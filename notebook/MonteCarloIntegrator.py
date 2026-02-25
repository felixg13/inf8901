import drjit as dr
import mitsuba as mi

if __name__ == "__main__":
    mi.set_variant('cuda_ad_rgb', 'llvm_ad_rgb')


class MonteCarloIntegrator(mi.SamplingIntegrator):
   
    def __init__(self, props=mi.Properties()):
        super().__init__(props)
        self.max_depth = props.get('max_depth', 8)
        self.rr_depth = props.get('rr_depth', 5)
        self.hide_emitters = props.get('hide_emitters', False)
        
    def sample(self, scene, sampler, ray_, medium=None, aovs=None, active=True):
        ray = mi.Ray3f(ray_)
        throughput = mi.Spectrum(1.0)
        result = mi.Spectrum(0.0)
        eta = mi.Float(1.0)
        depth = mi.UInt32(0)
        valid_ray = mi.Bool(not self.hide_emitters and scene.environment() is not None)
        active = mi.Bool(active)
        
        prev_si = dr.zeros(mi.Interaction3f)
        prev_bsdf_pdf = mi.Float(1.0)
        prev_bsdf_delta = mi.Bool(True)
        
        def loop_body(ray, throughput, result, eta, depth, valid_ray, 
                     prev_si, prev_bsdf_pdf, prev_bsdf_delta, active):
            
            si = scene.ray_intersect(ray, active)
            
            emitter = si.emitter(scene)
            active_hit = active & si.is_valid()
            
            em_hit = active_hit & (emitter != None)
            ds = mi.DirectionSample3f(scene, si, prev_si)
            em_pdf = mi.Float(0.0)
            
            em_pdf = dr.select(~prev_bsdf_delta & em_hit,
                             scene.pdf_emitter_direction(prev_si, ds, ~prev_bsdf_delta & em_hit),
                             em_pdf)
            
            mis_bsdf = dr.select(prev_bsdf_delta, 1.0, self.mis_weight(prev_bsdf_pdf, em_pdf))
            em_contrib = dr.select(em_hit, 
                                  emitter.eval(si, prev_bsdf_pdf > 0.0) * mis_bsdf,
                                  mi.Spectrum(0.0))
            result = dr.fma(throughput, em_contrib, result)
            
            active_next = active_hit & (depth + 1 < self.max_depth)
            
            bsdf = si.bsdf(ray)
            bsdf_ctx = mi.BSDFContext()
            
            active_em = active_next & mi.has_flag(bsdf.flags(), mi.BSDFFlags.Smooth)
            
            ds = dr.zeros(mi.DirectionSample3f)
            em_weight = dr.zeros(mi.Spectrum)
            
            ds, em_weight = dr.select(active_em,
                scene.sample_emitter_direction(si, sampler.next_2d(active_em), True, active_em),
                (ds, em_weight))
            active_em &= ds.pdf != 0.0
            
            wo = si.to_local(ds.d)
            
            sample_1 = sampler.next_1d(active_next)
            sample_2 = sampler.next_2d(active_next)
            
            bsdf_sample, bsdf_weight = bsdf.sample(bsdf_ctx, si, sample_1, sample_2, active_next)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active_em)
            bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active_em)
            
            mis_em = dr.select(ds.delta, 1.0, self.mis_weight(ds.pdf, bsdf_pdf))
            em_contrib = bsdf_val * em_weight * mis_em
            result = dr.select(active_em, dr.fma(throughput, em_contrib, result), result)
            
            throughput = dr.select(active_next, throughput * bsdf_weight, throughput)
            eta = dr.select(active_next, eta * bsdf_sample.eta, eta)
            
            ray = dr.select(active_next, si.spawn_ray(si.to_world(bsdf_sample.wo)), ray)
            
            valid_ray |= active_hit & ~mi.has_flag(bsdf_sample.sampled_type, mi.BSDFFlags.Null)
            
            prev_si = dr.select(active_next, mi.Interaction3f(si), prev_si)
            prev_bsdf_pdf = dr.select(active_next, bsdf_sample.pdf, prev_bsdf_pdf)
            prev_bsdf_delta = dr.select(active_next, 
                mi.has_flag(bsdf_sample.sampled_type, mi.BSDFFlags.Delta), prev_bsdf_delta)
            
            depth = dr.select(si.is_valid(), depth + 1, depth)
            
            throughput_max = dr.max(throughput)
            rr_prob = dr.minimum(throughput_max * dr.square(eta), 0.95)
            rr_active = depth >= self.rr_depth
            rr_continue = sampler.next_1d(active_next) < rr_prob
            
            throughput = dr.select(rr_active, throughput / dr.detach(rr_prob), throughput)
            
            active = active_next & (~rr_active | rr_continue) & (throughput_max != 0.0)
            
            return ray, throughput, result, eta, depth, valid_ray, prev_si, prev_bsdf_pdf, prev_bsdf_delta, active
        
        ray, throughput, result, eta, depth, valid_ray, prev_si, prev_bsdf_pdf, prev_bsdf_delta, active = dr.while_loop(
            state=(ray, throughput, result, eta, depth, valid_ray,
                   prev_si, prev_bsdf_pdf, prev_bsdf_delta, active),
            cond=lambda ray, throughput, result, eta, depth, valid_ray,
                       prev_si, prev_bsdf_pdf, prev_bsdf_delta, active: active,
            body=loop_body,
            labels=("ray", "throughput", "result", "eta", "depth", "valid_ray",
                    "prev_si", "prev_bsdf_pdf", "prev_bsdf_delta", "active"),
            label="Path Tracer"
        )
        
        return dr.select(valid_ray, result, 0.0), valid_ray, []
    
    def mis_weight(self, pdf_a, pdf_b):
        pdf_a_sq = pdf_a * pdf_a
        pdf_b_sq = pdf_b * pdf_b
        w = pdf_a_sq / (pdf_a_sq + pdf_b_sq)
        return dr.detach(dr.select(dr.isfinite(w), w, 0.0))
    
    def to_string(self):
        return f"SimplePathTracer[max_depth={self.max_depth}, rr_depth={self.rr_depth}]"


mi.register_integrator("MonteCarlo", lambda props: MonteCarloIntegrator(props))


if __name__ == "__main__":
    scene = mi.load_dict(mi.cornell_box())
    integrator = mi.load_dict({'type': 'MonteCarlo'})
    image = mi.render(scene, integrator=integrator)
    image = mi.Bitmap(image)
    mi.util.write_bitmap("MyMonteCarloRender.png", image)
