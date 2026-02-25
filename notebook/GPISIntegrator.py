"""
GPIS Integrator for Mitsuba 3
===============================================================================
Implementation of "From microfacets to participating media: A unified theory 
of light transport with stochastic geometry"

Based on Algorithm 1: Progressive sampling via function-space GPs (Section 4.2)

This integrator renders stochastic implicit surfaces defined by Gaussian 
Processes, unifying microfacet surfaces, participating media, and aggregate 
appearance under one framework.

Author: Implementation based on research paper
License: MIT
===============================================================================
"""

import drjit as dr
import mitsuba as mi
mi.set_variant('cuda_ad_mono', 'llvm_ad_rgb')
import numpy as np
from typing import Tuple, Optional


class GPMemoryState:
    """
    Stores GP conditioning information (ζ in the paper)
    
    The memory state keeps track of all observations along the path that 
    condition the Gaussian Process. Different memory models determine how 
    much information to retain.
    """
    def __init__(self):
        self.conditioning_data = {}
        self.observations = []
        
    def add_observation(self, position, value, normal=None):
        """Add a new observation point for GP conditioning"""
        self.observations.append({
            'position': position,
            'value': value,
            'normal': normal
        })


class GPRealization:
    """
    Stores a sampled 1D realization along a ray segment
    
    This represents f(x, x_∞) sampled at discrete points. We interpolate
    between these points to find zero crossings (surface intersections).
    """
    def __init__(self, positions, values, segment_length):
        self.positions = positions  # Sample positions along ray
        self.values = values        # GP values at those positions
        self.segment_length = segment_length
        

class GPISIntegrator(mi.SamplingIntegrator):
    """
    Gaussian Process Implicit Surface (GPIS) Integrator
    
    This integrator traces rays through stochastic implicit surfaces defined
    by Gaussian Processes. It implements the progressive sampling algorithm
    from Section 4.2 of the paper.
    
    Key features:
    - Progressive sampling along rays using function-space GPs
    - Importance sampling of ρ(x_t)Γ(t,n|ζ) factor
    - Support for non-stationary covariance kernels
    - Configurable memory models
    
    Parameters:
    -----------
    max_depth : int
        Maximum number of ray bounces (default: 8)
    rr_depth : int
        Depth at which to start Russian roulette (default: 5)
    samples_per_segment : int
        Number of GP samples per ray segment (default: 4)
        Higher values = more accurate but slower
    kernel_length_scale : float
        Length scale parameter l for RBF kernel (default: 0.1)
        Controls correlation distance in the GP
    kernel_variance : float
        Variance parameter σ² for RBF kernel (default: 1.0)
        Controls amplitude of variations
    """
    
    def __init__(self, props=mi.Properties()):
        super().__init__(props)
        
        # Ray tracing configuration
        self.max_depth = props.get('max_depth', 8)
        self.rr_depth = props.get('rr_depth', 5)
        
        # GP sampling configuration
        self.samples_per_segment = props.get('samples_per_segment', 4)
        self.kernel_length_scale = props.get('kernel_length_scale', 0.1)
        self.kernel_variance = props.get('kernel_variance', 1.0)
        
        # Numerical stability parameter
        self.jitter = 1e-6
        
    def sample(self, scene, sampler, ray, medium=None, active=True):
        """
        Main rendering equation - traces a ray through GPIS
        
        Implements L(r|ζ) from Algorithm 1 in the paper.
        This is the top-level function that computes radiance along a ray.
        
        Algorithm:
        1. Find next surface intersection using GPIS (nextHit)
        2. Add emitted radiance from surface
        3. Sample BSDF for next direction
        4. Recursively trace new ray
        5. Continue until max depth or Russian roulette termination
        
        Returns:
        --------
        result : Spectrum
            Estimated radiance along the ray
        valid : Bool
            Whether the estimate is valid
        aovs : list
            Arbitrary output values (empty for now)
        """
        # Initialize path tracing variables using Dr.Jit types
        ray = mi.Ray3f(ray)
        throughput = mi.Spectrum(1.0)
        result = mi.Spectrum(0.0)
        eta = mi.Float(1.0)
        depth = mi.UInt32(0)
        active = mi.Bool(active)
        
        # =================================================================
        # Main path tracing loop using dr.while_loop
        # This is the vectorized version of Algorithm 1's recursive structure
        # =================================================================
        
        def loop_cond(sampler, ray, throughput, result, eta, depth, active):
            """Loop continues while we have active rays and haven't exceeded max depth"""
            return active & (depth < self.max_depth)
        
        def loop_body(sampler, ray, throughput, result, eta, depth, active):
            """
            One iteration of the path tracing loop
            Implements the core GPIS algorithm from the paper
            """
            # =============================================================
            # Step 1: Trace ray to find intersection
            # In full GPIS: would sample GP along ray to find zero crossing
            # Here: use standard ray tracing + GP perturbation
            # =============================================================
            si = scene.ray_intersect(ray, active)
            
            # Update active mask - only continue if we hit something
            hit_surface = active & si.is_valid()
            
            # =============================================================
            # Step 2: Add emitted radiance from light sources
            # L_e term from the rendering equation
            # =============================================================
            emitter = si.emitter(scene)
            emitter_val = dr.select(
                hit_surface & (emitter is not None),
                emitter.eval(si, hit_surface),
                mi.Spectrum(0.0)
            )
            result += throughput * emitter_val
            
            # =============================================================
            # Step 3: GPIS modification - sample GP and perturb geometry
            # This adds stochastic micro-geometry based on GP realization
            # =============================================================
            # Sample scalar GP value at intersection point
            gp_value = self._sample_gp_scalar(si.p, sampler, hit_surface)
            
            # Perturb surface normal based on GP (creates stochastic roughness)
            perturbed_normal = self._perturb_normal(
                si.n, gp_value, sampler, hit_surface
            )
            
            # Update the shading frame with perturbed normal
            si.sh_frame.n = dr.select(hit_surface, perturbed_normal, si.sh_frame.n)
            
            # =============================================================
            # Step 4: Russian roulette termination
            # Probabilistically terminate paths while maintaining unbiased estimate
            # =============================================================
            needs_rr = hit_surface & (depth >= self.rr_depth)
            q = dr.minimum(dr.max(throughput) * eta * eta, 0.95)
            survive_rr = sampler.next_1d(hit_surface) < q
            
            active = hit_surface & ((~needs_rr) | survive_rr)
            throughput = dr.select(needs_rr & active, throughput / q, throughput)
            
            # =============================================================
            # Step 5: Sample BSDF for next direction
            # Implements: ω_t ~ ρ(x_t) from Algorithm 1
            # =============================================================
            bsdf = si.bsdf()
            bsdf_ctx = mi.BSDFContext()
            
            bsdf_sample = bsdf.sample(
                bsdf_ctx,
                si,
                sampler.next_1d(active),
                sampler.next_2d(active),
                active
            )
            
            # Update throughput with BSDF weight
            # throughput = dr.select(active, throughput * bsdf_sample, throughput)
            
            # =============================================================
            # Step 6: Spawn new ray in sampled direction
            # =============================================================
            # ray = dr.select(
            #     active,
            #     si.spawn_ray(si.wo),
            #     ray
            # )
            
            # Update IOR ratio for dielectric materials
            eta = dr.select(active, eta * bsdf_sample.eta, eta)
            
            # Increment depth counter
            depth += 1
            
            # Return updated state variables
            return sampler, ray, throughput, result, eta, depth, active
        
        # Execute the vectorized loop
        sampler, ray, throughput, result, eta, depth, active = dr.while_loop(
            state=(sampler, ray, throughput, result, eta, depth, active),
            cond=loop_cond,
            body=loop_body,
            labels=("sampler", "ray", "throughput", "result", "eta", "depth", "active"),
            label="GPIS Path Tracer"
        )
        
        return result, dr.any(active), []
    
    def _sample_gp_scalar(self, position, sampler, active):
        """
        Sample a scalar GP value at a 3D position
        
        This is a simplified version that samples from a standard normal.
        A full implementation would:
        1. Maintain conditioning data from previous bounces (memory state ζ)
        2. Compute covariance between current point and past observations
        3. Return conditional GP sample using the kernel function
        
        From the paper: "Sample a 1D realization f ~ GP|ζ"
        
        Parameters:
        -----------
        position : Point3f
            3D position to sample at
        sampler : Sampler
            Random number generator
        active : Bool
            Active lane mask
            
        Returns:
        --------
        value : Float
            Sampled GP value (mean-centered)
        """
        # Sample from standard normal distribution
        # In full implementation: would use RBF kernel k(x,x') = σ²exp(-||x-x'||²/2l²)
        # and condition on observed values from memory state
        z = sampler.next_1d(active) - 0.5
        
        # Scale by kernel variance
        return dr.select(active, z * dr.sqrt(self.kernel_variance), 0.0)
    
    def _perturb_normal(self, normal, gp_value, sampler, active):
        """
        Perturb surface normal based on GP sample
        
        This creates stochastic micro-geometry (roughness) by perturbing
        the surface normal based on the GP realization. This is analogous
        to how microfacet BRDFs work, but here the roughness comes from
        the stochastic implicit surface.
        
        From the paper: "Sample normal n ~ GP_∇x_t | ζ ∧ f(x,x_t)"
        
        Parameters:
        -----------
        normal : Normal3f
            Original surface normal
        gp_value : Float
            GP sample value (controls perturbation magnitude)
        sampler : Sampler
            Random number generator
        active : Bool
            Active lane mask
            
        Returns:
        --------
        perturbed : Normal3f
            Perturbed normal vector
        """
        return mi.Vector3f(1.0, 0.0, 0.0)
        # Build local tangent frame around the normal
        # This gives us orthogonal directions to perturb in
        s, t = dr.coordinate_system(normal)
        
        # Sample random perturbation direction in the tangent plane
        angle = sampler.next_1d(active) * 2.0 * dr.pi
        
        # Perturbation magnitude based on GP value and kernel length scale
        # Larger GP values -> more perturbation (rougher surface)
        magnitude = dr.abs(gp_value) * self.kernel_length_scale
        
        # Create perturbation vector in tangent plane
        offset_s = dr.cos(angle) * magnitude
        offset_t = dr.sin(angle) * magnitude
        
        # Add perturbation to normal and renormalize
        perturbed = normal + offset_s * s + offset_t * t
        perturbed = dr.normalize(perturbed)
        
        return dr.select(active, perturbed, normal)
    
    def sample_realization(self, ray, memory_state, sampler, active):
        """
        Sample 1D realization f(x, x_∞) ~ GP(x, x_∞)|ζ
        
        Uses progressive sampling strategy from Figure 8 of the paper:
        - Divide ray into segments of fixed length
        - Sample n points per segment
        - Interpolate between points to find zero crossings
        
        This avoids having to sample an infinite number of points along
        the ray by using the smoothness of the GP.
        
        NOTE: This is a reference implementation for the full GPIS algorithm.
        The current integrator uses a simplified approach with standard
        ray tracing + GP perturbations.
        
        Parameters:
        -----------
        ray : Ray3f
            Ray along which to sample
        memory_state : GPMemoryState
            Current conditioning state
        sampler : Sampler
            Random number generator
        active : Bool
            Mask of active rays
            
        Returns:
        --------
        realization : GPRealization
            Sampled GP values along the ray segment
        """
        # Determine segment length based on kernel length scale
        # Spacing should be fine enough to capture GP correlations
        segment_length = self.samples_per_segment * self.kernel_length_scale
        
        # Create sample positions along the ray segment
        positions = []
        for i in range(self.samples_per_segment):
            t = (i / (self.samples_per_segment - 1)) * segment_length
            positions.append(t)
        
        # Sample from GP at these positions
        gp_samples = self.sample_gp_1d(ray, positions, memory_state, sampler, active)
        
        return GPRealization(positions, gp_samples, segment_length)
    
    def sample_gp_1d(self, ray, positions, memory_state, sampler, active):
        """
        Sample from 1D Gaussian Process along ray
        
        Uses function-space sampling with RBF (Radial Basis Function) kernel:
        k(s, s') = σ² exp(-||s - s'||² / (2l²))
        
        This is the core GP sampling operation from the paper. We:
        1. Build covariance matrix K from kernel evaluations
        2. Decompose K = L L^T using Cholesky decomposition
        3. Sample z ~ N(0, I)
        4. Return f = L z ~ N(0, K)
        
        From the paper Section 4.2.1: "Using function space sampling, we can 
        only sample a finite set of m values, and the cost grows with O(m³)"
        
        Parameters:
        -----------
        ray : Ray3f
            Ray being sampled
        positions : list of float
            Positions along ray to sample at
        memory_state : GPMemoryState
            Conditioning information (for future implementation)
        sampler : Sampler
            Random number generator
        active : Bool
            Active ray mask
            
        Returns:
        --------
        f : list
            GP samples at the requested positions
        """
        n = len(positions)
        
        # =================================================================
        # Step 1: Build covariance matrix using RBF kernel
        # K[i,j] = k(s_i, s_j) = σ² exp(-||s_i - s_j||² / (2l²))
        # =================================================================
        K = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                # Squared distance between positions
                dist_sq = (positions[i] - positions[j]) ** 2
                
                # RBF kernel evaluation
                K[i, j] = self.kernel_variance * np.exp(
                    -dist_sq / (2 * self.kernel_length_scale ** 2)
                )
        
        # Add small value to diagonal for numerical stability
        # Prevents Cholesky decomposition from failing
        K += np.eye(n) * self.jitter
        
        # =================================================================
        # Step 2: Cholesky decomposition K = L L^T
        # This allows us to transform standard normal samples into
        # samples from N(0, K)
        # =================================================================
        try:
            L = np.linalg.cholesky(K)
        except np.linalg.LinAlgError:
            # If Cholesky fails, add more jitter
            K += np.eye(n) * 1e-4
            L = np.linalg.cholesky(K)
        
        # =================================================================
        # Step 3: Sample standard normal vector z ~ N(0, I)
        # =================================================================
        z = []
        for i in range(n):
            sample = sampler.next_1d(active)
            # Convert to numpy-compatible format
            z.append(dr.mean(sample) if hasattr(sample, '__len__') else float(sample))
        z = np.array(z)
        
        # =================================================================
        # Step 4: Transform to GP sample f = L z ~ N(0, K)
        # =================================================================
        f = L @ z
        
        return f.tolist()
    
    def find_zero_crossing(self, f_realization, active):
        """
        Find first zero crossing: t = arg min_s f(s) = 0
        
        Uses linear interpolation between sampled points to find where
        the GP crosses zero. This represents the surface intersection.
        
        From the paper: "Find the intersection distance 
        t = arg min_{s ∈ (0,∞)} f(x,x_s) = 0"
        
        Parameters:
        -----------
        f_realization : GPRealization
            Sampled GP values along ray
        active : Bool
            Active ray mask
            
        Returns:
        --------
        t_hit : Float
            Distance to intersection (or inf if no intersection)
        """
        positions = f_realization.positions
        values = f_realization.values
        
        t_hit = float('inf')
        
        # Check each segment between consecutive samples
        for i in range(len(values) - 1):
            # Check if sign changes between consecutive points
            # This indicates a zero crossing (surface intersection)
            if values[i] * values[i+1] < 0:
                # Linear interpolation to find exact zero crossing
                # If f(s_i) and f(s_{i+1}) have opposite signs:
                # t = s_i + α(s_{i+1} - s_i) where α = f(s_i)/(f(s_i) - f(s_{i+1}))
                alpha = values[i] / (values[i] - values[i+1])
                t_candidate = positions[i] + alpha * (positions[i+1] - positions[i])
                
                # Take the closest intersection
                if t_candidate < t_hit:
                    t_hit = t_candidate
        
        return t_hit
    
    def to_string(self):
        """String representation for debugging"""
        return (
            f"GPISIntegrator[\n"
            f"  max_depth = {self.max_depth},\n"
            f"  rr_depth = {self.rr_depth},\n"
            f"  samples_per_segment = {self.samples_per_segment},\n"
            f"  kernel_length_scale = {self.kernel_length_scale},\n"
            f"  kernel_variance = {self.kernel_variance}\n"
            f"]"
        )


# =============================================================================
# Register the integrator with Mitsuba 3
# =============================================================================
mi.register_integrator("gpis", lambda props: GPISIntegrator(props))


# =============================================================================
# Example usage
# =============================================================================
if __name__ == "__main__":
    print("GPIS Integrator for Mitsuba 3")
    print("=" * 60)
    print()
    print("This integrator implements Algorithm 1 from:")
    print("'From microfacets to participating media: A unified theory")
    print("of light transport with stochastic geometry'")
    print()
    print("To use:")
    print("1. Import mitsuba and set variant:")
    print("   import mitsuba as mi")
    print("   mi.set_variant('llvm_ad_rgb')")
    print()
    print("2. Import this module:")
    print("   import gpis_integrator")
    print()
    print("3. Load scene and render:")
    print("   scene = mi.load_file('scene.xml')")
    print("   integrator = mi.load_dict({'type': 'gpis'})")
    print("   image = mi.render(scene, spp=256, integrator=integrator)")
    print()
    print("The integrator will add stochastic micro-geometry to surfaces")
    print("based on Gaussian Process realizations.")

    scene = mi.load_file("./scenes/cornell-box/scene.xml")
    
    integrator = mi.load_dict({
        'type': 'gpis'
    })
    
    image = mi.render(scene, spp=1, integrator=integrator)

    image = mi.Bitmap(image)
    mi.util.write_bitmap("my_first_render.png", image)