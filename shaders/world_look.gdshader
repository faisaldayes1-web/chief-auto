// The shared "Chief Auto" look for the world renders (lot, showroom, garage, office, desks):
// day -> night crossfade with the night render (only the sky and outdoors change; the night render keeps the
// interiors lit), a gentle warm/cool colour grade, a soft bloom on highlights and a vignette.
shader_type canvas_item;

uniform sampler2D night_tex : filter_linear, source_color;
uniform float night : hint_range(0.0, 1.0) = 0.0;
uniform vec4 tint : source_color = vec4(1.0);     // dusk warmth (day -> sunset)
uniform float bloom = 0.14;        // additive glow on highlights only; the picture itself is never blurred
uniform float vignette = 0.32;
uniform float grade = 1.0;
uniform vec2 texel = vec2(0.000625, 0.0011);       // 1 / render size

// COLOR in fragment() already holds texture × modulate, so multiplying by it again squared the picture
// (~35-45% darker): keep the plain vertex/modulate colour from vertex() instead.
varying vec4 modulate_col;

void vertex() {
	modulate_col = COLOR;
}

vec3 world_at(sampler2D day, vec2 uv) {
	vec3 d = texture(day, uv).rgb * tint.rgb;
	vec3 n = texture(night_tex, uv).rgb;
	return mix(d, n, night);
}

void fragment() {
	vec4 base = texture(TEXTURE, UV);
	// the base image is sampled once at full resolution (no LOD bias); only the glow reads neighbours
	vec3 c = world_at(TEXTURE, UV);
	// bloom: thresholded highlights from a 12-tap ring at two radii
	vec3 glow = vec3(0.0);
	for (int i = 0; i < 6; i++) {
		float a = float(i) * 1.0472;
		vec2 o = vec2(cos(a), sin(a)) * texel;
		glow += max(world_at(TEXTURE, UV + o * 5.0) - 0.8, 0.0);
		glow += max(world_at(TEXTURE, UV + o * 12.0) - 0.8, 0.0) * 0.6;
	}
	c += glow / 9.6 * bloom * (1.0 + night * 1.5);
	// grade: a touch of S-curve contrast, warm highlights, cool shadows, a little more saturation
	vec3 g = c;
	float l = dot(g, vec3(0.299, 0.587, 0.114));
	g = mix(vec3(l), g, 1.08);
	g = g + (g - 0.5) * 0.06 * (1.0 - abs(g - 0.5) * 2.0);
	g += vec3(0.018, 0.008, -0.012) * smoothstep(0.45, 1.0, l) + vec3(-0.01, 0.0, 0.018) * (1.0 - smoothstep(0.0, 0.35, l));
	c = mix(c, g, grade);
	// vignette on the screen, not the texture, so every layer shares it
	vec2 q = SCREEN_UV - 0.5;
	float v = 1.0 - vignette * smoothstep(0.25, 0.85, dot(q, q) * 2.2);
	COLOR = vec4(clamp(c * v, 0.0, 1.0), base.a) * modulate_col;
}
