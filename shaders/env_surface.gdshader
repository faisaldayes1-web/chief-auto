// Glass, chrome, rims and other glossy trim with reflections from an equirect env map (see env_reflect.gdshaderinc).
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;
#include "res://shaders/env_reflect.gdshaderinc"

uniform vec4 albedo : source_color = vec4(0.8, 0.8, 0.8, 1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, hint_default_white;
uniform float metallic_v = 1.0;
uniform float rough_v = 0.15;
uniform sampler2D env_map : source_color, filter_linear_mipmap, repeat_enable, hint_default_black;
uniform float env_strength = 1.0;
uniform vec3 glow = vec3(0.0);

void fragment() {
	vec4 a = albedo * texture(albedo_tex, UV);
	ALBEDO = a.rgb;
	METALLIC = metallic_v;
	ROUGHNESS = rough_v;
	vec3 env = env_sample(env_map, NORMAL, VIEW, INV_VIEW_MATRIX, rough_v);
	float f = env_fresnel(NORMAL, VIEW, 0.04);
	// metals tint the reflection with their colour; dielectrics reflect white, mostly at grazing angles
	vec3 spec = mix(vec3(f), a.rgb, metallic_v) * (1.0 - rough_v * 0.7);
	EMISSION = env * spec * env_strength + glow;
}
