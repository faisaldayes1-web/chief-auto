// Car paint with damage you can see: rust, scratches, dents and road grime, all driven per panel.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec3 paint_color : source_color = vec3(0.6);
uniform float metallic_v = 0.35;
uniform float rough_v = 0.28;
uniform float rust = 0.0;
uniform float scratch = 0.0;
uniform float dent = 0.0;
uniform float dirt = 0.0;
uniform vec4 highlight : source_color = vec4(0.0);
uniform float seed = 0.0;

varying vec3 lp;

void vertex() {
	lp = VERTEX;
}

float hash(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
				   mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
			   mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
				   mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float fbm(vec3 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) {
		v += a * noise(p);
		p *= 2.03;
		a *= 0.5;
	}
	return v;
}

void fragment() {
	vec3 p = lp + vec3(seed * 7.13, seed * 3.7, seed * 1.9);
	vec3 col = paint_color;
	float r = rough_v;
	float m = metallic_v;

	// road grime low on the body
	float low = 1.0 - smoothstep(0.15, 0.75, lp.y);
	float g = dirt * low * smoothstep(0.35, 0.75, fbm(p * 4.0));
	col = mix(col, vec3(0.23, 0.2, 0.16), g * 0.85);
	r = mix(r, 0.85, g);

	// scratches: thin streaks along the body
	float s1 = noise(vec3(p.x * 3.0, p.y * 90.0, p.z * 3.0));
	float s2 = noise(vec3(p.x * 70.0 + 3.0, p.y * 4.0, p.z * 70.0));
	float zone = smoothstep(0.45, 0.7, fbm(p * 1.3 + 4.0));
	float sc = scratch * zone * max(smoothstep(0.86, 0.9, s1), smoothstep(0.9, 0.93, s2));
	col = mix(col, vec3(0.78, 0.78, 0.76), sc);
	r = mix(r, 0.6, sc);
	m = mix(m, 0.0, sc);

	// rust blooms from patches, worse near the bottom
	float rn = fbm(p * 2.2 + 11.0) + low * 0.18;
	float rm = smoothstep(1.02 - rust * 0.55, 1.08 - rust * 0.55, rn) * step(0.001, rust);
	vec3 rustc = mix(vec3(0.33, 0.12, 0.04), vec3(0.55, 0.26, 0.08), fbm(p * 18.0));
	float bubble = smoothstep(0.95 - rust * 0.55, 1.02 - rust * 0.55, rn) * (1.0 - rm);
	col = mix(col, col * 0.7, bubble * 0.6);
	col = mix(col, rustc, rm);
	r = mix(r, 0.95, rm);
	m = mix(m, 0.0, rm);

	// dents: wobble the normal inside a couple of soft blobs
	float dz = smoothstep(0.55, 0.75, fbm(p * 1.1 + 23.0)) * dent;
	vec3 wob = vec3(noise(p * 9.0) - 0.5, noise(p * 9.0 + 17.0) - 0.5, noise(p * 9.0 + 31.0) - 0.5);
	NORMAL = normalize(NORMAL + wob * dz * 1.6);

	ALBEDO = mix(col, highlight.rgb, highlight.a * 0.35);
	EMISSION = highlight.rgb * highlight.a * 0.35;
	METALLIC = m;
	ROUGHNESS = r;
}
