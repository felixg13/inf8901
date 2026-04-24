import drjit as dr
import mitsuba as mi

mi.set_variant("scalar_rgb")


class myMedium(mi.Medium):
    def __init__(self, props=mi.Properties()):
        super().__init__(props)
        self.center = props.get("center", mi.ScalarPoint3f(0, 0, 0))
        self.radius = props.get("radius", 1.0)
        self.step_size = props.get("step_size", 0.05)
        self.max_steps = props.get("max_steps", 100)
        self.epsilon = 1e-4

    def has_homogeneous_spectral_response(self):
        return True

    def has_homogeneous_density(self):
        return False

    def use_emitter_sampling(self):
        return False

    def _signed_distance(self, p, active):
        p_local = p - mi.Point3f(self.center)
        distance = dr.norm(p_local) - mi.Float(self.radius)
        return dr.select(active, distance, mi.Float(dr.inf))

    def sample_interaction(self, ray, sample, channel, active):
        print("sample_interaction called!")
        active = mi.Bool(active)

        prev_t = mi.Float(0.0)
        prev_distance = self._signed_distance(ray.o, active)
        t_hit = mi.Float(ray.maxt)
        hit_found = mi.Bool(False)

        for step in range(self.max_steps):
            t_current = dr.minimum(prev_t + self.step_size, ray.maxt)
            p = ray(t_current)
            distance = self._signed_distance(p, active)

            crossed = (prev_distance * distance < 0.0) & active & ~hit_found

            dist_abs_prev = dr.abs(prev_distance)
            dist_abs_curr = dr.abs(distance)
            denom = dist_abs_prev + dist_abs_curr
            alpha = dr.select(
                denom > self.epsilon, dist_abs_prev / denom, mi.Float(0.5)
            )
            t_candidate = prev_t + alpha * (t_current - prev_t)

            valid_hit = crossed & (t_candidate >= 0.0) & (t_candidate <= ray.maxt)
            t_hit = dr.select(valid_hit, t_candidate, t_hit)
            hit_found = hit_found | valid_hit

            prev_distance = distance
            prev_t = t_current

            if dr.all(~active | (t_current >= ray.maxt)):
                break

        mei = dr.zeros(mi.MediumInteraction3f)
        mei.t = dr.select(hit_found, t_hit, mi.Float(dr.inf))
        mei.p = ray(dr.select(hit_found, t_hit, ray.maxt))
        mei.wi = -ray.d
        mei.sh_frame = mi.Frame3f(mei.wi)
        mei.time = ray.time
        mei.wavelengths = ray.wavelengths
        mei.mint = ray.mint

        return mei, hit_found & active

    def get_majorant(self, mei, active=True):
        return mi.Spectrum(1.0)

    def get_scattering_coefficients(self, mei, active=True):
        print("coeffeicient")
        active = mi.Bool(active)
        inside = (dr.norm(mei.p - mi.Point3f(self.center)) < self.radius) & active
        sigma_s = dr.select(inside, mi.Spectrum(0.8), mi.Spectrum(0.0))
        sigma_t = dr.select(inside, mi.Spectrum(1.0), mi.Spectrum(0.0))
        sigma_n = mi.Spectrum(0.0)
        return sigma_s, sigma_n, sigma_t

    def eval_tr(self, mei, ds, active=True):
        distance = mei.t
        absorption = dr.exp(-distance * 0.1)
        return dr.select(mi.Bool(active), mi.Spectrum(absorption), mi.Spectrum(0.0))

    def pdf_extinction(self, mei, active=True):
        return dr.select(mi.Bool(active), mi.Float(0.0), mi.Float(0.0))

    def intersect_aabb(self, ray):
        print("test")
        # Unit cube is [-1, 1] in all axes
        inv_d = dr.rcp(ray.d)

        t1 = (mi.Point3f(-1, -1, -1) - ray.o) * inv_d
        t2 = (mi.Point3f(1, 1, 1) - ray.o) * inv_d

        t_near = dr.maximum(
            dr.maximum(dr.minimum(t1.x, t2.x), dr.minimum(t1.y, t2.y)),
            dr.minimum(t1.z, t2.z),
        )

        t_far = dr.minimum(
            dr.minimum(dr.maximum(t1.x, t2.x), dr.maximum(t1.y, t2.y)),
            dr.maximum(t1.z, t2.z),
        )

        active = (t_far >= t_near) & (t_far >= 0.0)
        t_near = dr.maximum(t_near, mi.Float(0.0))

        return active, t_near, t_far

    def to_string(self):
        return (
            f"myMedium[\n"
            f"  center = {self.center},\n"
            f"  radius = {self.radius},\n"
            f"  step_size = {self.step_size},\n"
            f"  max_steps = {self.max_steps}\n"
            f"]"
        )


mi.register_medium("mymedium", lambda props: myMedium(props))
