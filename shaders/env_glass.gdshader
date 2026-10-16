// Tinted car / window glass with reflections from an equirect env map (see env_reflect.gdshaderinc).
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_back, specular_schlick_ggx;
#include "res://shaders/env_reflect.gdshaderinc"

uniform vec4 tint : source_color = vec4(0.02, 0.025, 0.03, 0.8);
uniform float rough_v = 0.03;
uniform sampler2D env_map : source_color, filter_linear_mipmap, repeat_enable, hint_default_black;
uniform float env_strength = 1.0;
uniform vec3 glow = vec3(0.0);

void fragment() {
	float f = env_fresnel(NORMAL, VIEW, 0.06);
	vec3 env = env_sample(env_map, NORMAL, VIEW, INV_VIEW_MATRIX, rough_v);
	ALBEDO = tint.rgb;
	ROUGHNESS = rough_v;
	METALLIC = 0.0;
	SPECULAR = 0.8;
	EMISSION = env * mix(0.12, 1.0, f) * env_strength + glow;
	ALPHA = clamp(tint.a + f * 0.4, 0.0, 1.0);
}
