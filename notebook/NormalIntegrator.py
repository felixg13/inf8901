import mitsuba as mi
import drjit as dr

class NormalIntegrator(mi.SamplingIntegrator):

    def __init__(self, props=mi.Properties()):
        super().__init__(props)
    
    def sample(self, scene, sampler, ray, medium=None, active=True):

        si = scene.ray_intersect(ray, active)
        
        result = dr.select(
            si.is_valid(),
            (si.n + 1.0) * 0.5,
            mi.Color3f(0.0)
        )
        
        return (result, si.is_valid(), [])
    
    def to_string(self):
        return "SimpleIntegrator[]"