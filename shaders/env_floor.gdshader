// Polished stone floor: Poly Haven albedo / normal / roughness maps in world XZ plus reflections of the hall
// from an equirect env map (see env_reflect.gdshaderinc), so it still reads as polished on the web build.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;
#include "res://shaders/env_reflect.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 tint : source_color = vec3(1.0);
uniform float tile = 3.6;          // metres the texture covers
uniform float rough_mul = 0.35;
uniform float normal_depth = 0.5;
uniform sampler2D env_map : source_color, filter_linear_mipmap, repeat_enable, hint_default_black;
uniform float env_strength = 1.0;
// baked Cycles lighting on UV2 (tools: tests/_extract_bake.gd); 0.5 is neutral, so it is applied x2
uniform sampler2D lightmap : source_color, filter_linear, hint_default_white;
uniform float lightmap_k = 0.0;
// per camera view (Showroom3D.GLARE): the sun's reflection in the polish, held back where the camera looks down it
uniform float spec_k = 0.35;

varying vec3 wp;
void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = wp.xz / tile;
	ALBEDO = texture(albedo_tex, uv).rgb * tint;
	ALBEDO *= mix(vec3(1.0), texture(lightmap, UV2).rgb * 2.0, lightmap_k);
	float r = clamp(texture(rough_tex, uv).r * rough_mul, 0.02, 1.0);
	ROUGHNESS = r;
	SPECULAR = 0.5 * spec_k;
	NORMAL_MAP = texture(normal_tex, uv).rgb;
	NORMAL_MAP_DEPTH = normal_depth;
	float f = env_fresnel(NORMAL, VIEW, 0.04);
	vec3 env = env_sample(env_map, NORMAL, VIEW, INV_VIEW_MATRIX, r);
	EMISSION = env * f * (1.0 - r) * env_strength * mix(0.6, 1.0, spec_k);
}
