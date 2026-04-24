"""
Simple Volumetric Integrator - Demonstrates ray marching medium

This integrator actively samples the participating medium at each step,
allowing the myMedium.sample_interaction() ray marching to be called
and detect the implicit sphere surface.
"""

import drjit as dr
import mitsuba as mi

mi.set_variant('llvm_ad_rgb')


class VolumetricPathTracer(mi.SamplingIntegrator):
    """
    Simple volumetric path tracer that actively samples the medium.
    
    Unlike the standard path integrator, this one calls sample_interaction()
    to detect volumetric events (like implicit surfaces via ray marching).
    """
    
    def __init__(self, props=mi.Properties()):
        super().__init__(props)
        self.max_depth = props.get('max_depth', 4)
        self.rr_depth = props.get('rr_depth', 2)
    
    def sample(self, scene, sampler, ray, medium=None, active=True):
        """
        Main volumetric rendering equation.
        
        Demonstrates the myMedium ray marching by calling sample_interaction
        to detect implicit surfaces.
        """
        ray = mi.Ray3f(ray)
        throughput = mi.Spectrum(1.0)
        result = mi.Spectrum(0.0)
        eta = mi.Float(1.0)
        depth = mi.UInt32(0)
        active = mi.Bool(active)
        
        # ====================================================================
        # DEMONSTRATION: Call ray marching medium sample_interaction
        # ====================================================================
        if medium is not None:
            mi_ptr = medium.sample_interaction(ray, sampler, 0, active)
            
            # Color based on whether ray hit implicit surface
            hit_surface = mi_ptr.is_valid() & active
            surface_color = dr.select(
                hit_surface,
                mi.Spectrum([0.2, 0.8, 0.2]),  # Green for hit
                mi.Spectrum([0.8, 0.2, 0.2])   # Red for no hit
            )
            result = result + throughput * surface_color
        
        # ====================================================================
        # Regular geometry path tracing
        # ====================================================================
        ray = mi.Ray3f(ray)
        throughput = mi.Spectrum(1.0)
        result = mi.Spectrum(0.0)
        eta = mi.Float(1.0)
        depth = mi.UInt32(0)
        active = mi.Bool(active)
        
        def loop_cond(sampler, ray, throughput, result, eta, depth, active):
            return active & (depth < self.max_depth)
        
        def loop_body(sampler, ray, throughput, result, eta, depth, active):
            # Try regular geometry
            si = scene.ray_intersect(ray, active)
            has_geometry = si.is_valid() & active
            
            # Hit geometry
            if dr.any(has_geometry):
                emitter = si.emitter(scene)
                emitter_val = dr.select(
                    has_geometry & (emitter is not None),
                    emitter.eval(si, has_geometry),
                    mi.Spectrum(0.0)
                )
                result = dr.select(has_geometry, result + throughput * emitter_val, result)
                
                # Russian roulette
                needs_rr = has_geometry & (depth >= self.rr_depth)
                q = dr.minimum(dr.max(throughput) * eta * eta, 0.95)
                survive_rr = sampler.next_1d(has_geometry) < q
                
                active = has_geometry & ((~needs_rr) | survive_rr)
                throughput = dr.select(needs_rr & active, throughput / q, throughput)
                
                # Sample BSDF
                bsdf = si.bsdf()
                bsdf_ctx = mi.BSDFContext()
                
                bsdf_sample = bsdf.sample(
                    bsdf_ctx, si,
                    sampler.next_1d(active),
                    sampler.next_2d(active),
                    active
                )
                
                ray = dr.select(active, si.spawn_ray(bsdf_sample.wo), ray)
                eta = dr.select(active, eta * bsdf_sample.eta, eta)
            
            depth += 1
            return sampler, ray, throughput, result, eta, depth, active
        
        # Execute loop
        sampler, ray, throughput, result, eta, depth, active = dr.while_loop(
            state=(sampler, ray, throughput, result, eta, depth, active),
            cond=loop_cond,
            body=loop_body,
            labels=("sampler", "ray", "throughput", "result", "eta", "depth", "active"),
            label="Volumetric Path Tracer"
        )
        
        return result, dr.any(active), []
    
    def to_string(self):
        return f"VolumetricPathTracer[max_depth={self.max_depth}]"


# Register integrator
mi.register_integrator("volumetric", lambda props: VolumetricPathTracer(props))
