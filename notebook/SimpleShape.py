import drjit as dr
import mitsuba as mi

if __name__ == "__main__":
    mi.set_variant('cuda_ad_rgb', 'llvm_ad_rgb')


class SimpleSphere(mi.Shape):
    
    def __init__(self, props):
        super().__init__()
        
        self.m_center = props.get('center', mi.ScalarPoint3f(0, 0, 0))
        self.m_radius = props.get('radius', 1.0)
        
        self.m_to_world = mi.ScalarTransform4f.translate(self.m_center)
        self.m_to_object = self.m_to_world.inverse()
        
    def bbox(self, index=0):
        r = self.m_radius
        return mi.ScalarBoundingBox3f(
            self.m_center - mi.ScalarVector3f(r, r, r),
            self.m_center + mi.ScalarVector3f(r, r, r)
        )
    
    def ray_intersect_preliminary(self, ray, prim_index=0, active=True):
        active = mi.Bool(active)
        
        oc = ray.o - mi.Point3f(self.m_center)
        
        a = dr.squared_norm(ray.d)
        half_b = dr.dot(oc, ray.d)
        c = dr.squared_norm(oc) - self.m_radius * self.m_radius
        
        discriminant = half_b * half_b - a * c
        
        hit = (discriminant >= 0.0) & active
        
        sqrt_d = dr.sqrt(dr.maximum(discriminant, 0.0))
        t1 = (-half_b - sqrt_d) / a
        t2 = (-half_b + sqrt_d) / a
        
        t = dr.select(t1 > ray.mint, t1, t2)
        hit &= (t >= ray.mint) & (t <= ray.maxt)
        
        pi = dr.zeros(mi.PreliminaryIntersection3f)
        pi.t = dr.select(hit, t, dr.inf)
        pi.prim_uv = mi.Point2f(0.0)
        pi.prim_index = mi.UInt32(0)
        pi.shape = self
        
        return pi
    
    def compute_surface_interaction(self, ray, pi, ray_flags=mi.RayFlags.All, active=True):
        active = mi.Bool(active)
        
        si = dr.zeros(mi.SurfaceInteraction3f)
        si.t = dr.select(active, pi.t, dr.inf)
        
        si.p = ray(pi.t)
        
        outward_normal = dr.normalize(si.p - mi.Point3f(self.m_center))
        si.n = outward_normal
        si.sh_frame = mi.Frame3f(si.n)
        
        theta = dr.acos(dr.clamp(outward_normal.z, -1.0, 1.0))
        phi = dr.atan2(outward_normal.y, outward_normal.x)
        phi = dr.select(phi < 0, phi + 2.0 * dr.pi, phi)
        
        si.uv = mi.Point2f(phi / (2.0 * dr.pi), theta / dr.pi)
        
        si.dp_du = mi.Vector3f(
            -2.0 * dr.pi * outward_normal.y,
            2.0 * dr.pi * outward_normal.x,
            0.0
        )
        si.dp_dv = dr.pi * mi.Vector3f(
            outward_normal.z * dr.cos(phi),
            outward_normal.z * dr.sin(phi),
            -dr.sin(theta)
        )
        
        si.shape = self
        si.prim_index = mi.UInt32(0)
        si.instance = None
        
        si.time = ray.time
        si.wavelengths = ray.wavelengths
        
        return si
    
    def surface_area(self):
        return 4.0 * dr.pi * self.m_radius * self.m_radius
    
    def sample_position(self, time, sample, active=True):
        ps = dr.zeros(mi.PositionSample3f)
        
        z = 1.0 - 2.0 * sample.x
        r = dr.sqrt(dr.maximum(0.0, 1.0 - z * z))
        phi = 2.0 * dr.pi * sample.y
        
        local_p = mi.Vector3f(r * dr.cos(phi), r * dr.sin(phi), z)
        
        ps.p = mi.Point3f(self.m_center) + self.m_radius * local_p
        ps.n = local_p
        ps.pdf = 1.0 / self.surface_area()
        ps.time = time
        ps.delta = False
        
        theta = dr.acos(dr.clamp(z, -1.0, 1.0))
        ps.uv = mi.Point2f(phi / (2.0 * dr.pi), theta / dr.pi)
        
        return ps
    
    def pdf_position(self, ps, active=True):
        return 1.0 / self.surface_area()
    
    def primitive_count(self):
        return 1
    
    def effective_primitive_count(self):
        return 1
    
    def to_string(self):
        return f"SimpleSphere[center={self.m_center}, radius={self.m_radius}]"


mi.register_shape("simple_sphere", SimpleSphere)


if __name__ == "__main__":
    mi.set_variant('llvm_ad_rgb')
    
    scene_dict = {
        'type': 'scene',
        'integrator': {
            'type': 'path',
            'max_depth': 8
        },
        'sensor': {
            'type': 'perspective',
            'fov': 45,
            'to_world': mi.ScalarTransform4f.look_at(
                origin=[0, 0, 5],
                target=[0, 0, 0],
                up=[0, 1, 0]
            ),
            'film': {
                'type': 'hdrfilm',
                'width': 512,
                'height': 512,
                'rfilter': {'type': 'gaussian'}
            }
        },
        'sphere1': {
            'type': 'simple_sphere',
            'center': [0, 0, 0],
            'radius': 1.0,
            'bsdf': {
                'type': 'diffuse',
                'reflectance': {'type': 'rgb', 'value': [0.8, 0.2, 0.2]}
            }
        },
        'sphere2': {
            'type': 'simple_sphere',
            'center': [-1.5, 0.5, 0],
            'radius': 0.5,
            'bsdf': {
                'type': 'diffuse',
                'reflectance': {'type': 'rgb', 'value': [0.2, 0.8, 0.2]}
            }
        },
        'light': {
            'type': 'point',
            'position': [3, 5, 3],
            'intensity': {'type': 'rgb', 'value': [50, 50, 50]}
        },
        'env': {
            'type': 'constant',
            'radiance': {'type': 'rgb', 'value': [0.1, 0.1, 0.15]}
        }
    }
    
    scene = mi.load_dict(scene_dict)
    
    image = mi.render(scene, spp=64)
    
    mi.util.write_bitmap("output.exr", image)
    print("Rendered image saved to output.exr")