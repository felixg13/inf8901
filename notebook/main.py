"""
Main Rendering Script - myMedium Ray Marching Sphere

This script demonstrates rendering a scene containing the myMedium participating
medium with a centered sphere. The scene includes:

1. A participating medium (myMedium) with a centered sphere
2. A simple geometric shape (box) for reference
3. Point lighting
4. A perspective camera
5. Path tracing with the standard integrator

The myMedium class uses ray marching to detect intersections with an implicit
sphere surface, demonstrating full control over sample_interaction.
"""

import mitsuba as mi
from myMedium import myMedium  # noqa # pylint: disable=unused-import

if __name__ == "__main__":
    # Set Mitsuba variant
    print("Setting up Mitsuba 3...")
    mi.set_variant("scalar_rgb")

    # =========================================================================
    # Build scene using Cornell Box
    # =========================================================================
    print("\nBuilding scene...")
    scene_dict = mi.cornell_box()

    del scene_dict["small-box"]
    del scene_dict["large-box"]

    scene_dict["integrator"] = {"type": "volpath", "max_depth": 8}

    scene_dict["floating_box"] = {
        "type": "cube",
        "to_world": mi.ScalarTransform4f.scale(0.3),
        "interior": {
            "type": "homogenous",
            "radius": 0.5,
            "step_size": 0.1,
            "max_steps": 100,
        },
        "bsdf": {"type": "null"},
    }

    scene = mi.load_dict(scene_dict)
    image = mi.render(scene, spp=128)

    png_path = "mymedium_render.png"
    image_bitmap = mi.Bitmap(image)
    mi.util.write_bitmap(png_path, image_bitmap)
    print(f"✓ Preview image saved to {png_path}")
