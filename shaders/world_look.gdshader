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
// Faisal's "crisp painted illustration" picks (lot, office, sales desk): a 4-sector Kuwahara filter flattens the
// render into brush-like patches, a luminance contour inks the shapes, colours get a painted lift, and a fine
// canvas grain sits on top. 0 = the plain render (garage, apartment).
uniform float paint : hint_range(0.0, 1.0) = 0.0;
uniform float paint_radius = 4.0;   // in texels of the background render
uniform float ink = 0.55;           // contour strength
uniform float sun_exposure = 1.55;  // painted views only: exposure lift toward the bright picks

// COLOR in fragment() already holds texture × modulate, so multiplying by it again squared the picture
// (~35-45% darker): keep the plain vertex/modulate colour from vertex() instead.
varying vec4 modulate_col;

void vertex() {
	modulate_col = COLOR;
}

// Takes the day colour already sampled in fragment(): passing the built-in TEXTURE into a function as a
// sampler2D argument made Godot 4.3's shader compiler log "custom_samplers.has(...tex_builtin)" on import.
vec3 world_at(vec3 day, vec2 uv) {
	vec3 n = texture(night_tex, uv).rgb;
	return mix(day * tint.rgb, n, night);
}

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

void fragment() {
	vec4 base = texture(TEXTURE, UV);
	// the base image is sampled once at full resolution (no LOD bias); only the glow reads neighbours
	vec3 day = base.rgb;
	if (paint > 0.001) {
		// Kuwahara: mean of the least-varied of four 3x3 quadrants (radius scaled), so flat areas become strokes
		vec3 best = day;
		float best_v = 1e9;
		for (int q = 0; q < 4; q++) {
			vec2 sg = vec2(q == 1 || q == 3 ? 1.0 : -1.0, q >= 2 ? 1.0 : -1.0);
			vec3 sum = vec3(0.0);
			vec3 sq = vec3(0.0);
			for (int j = 0; j < 3; j++) {
				for (int i = 0; i < 3; i++) {
					vec3 t = texture(TEXTURE, UV + sg * vec2(float(i), float(j)) * texel * paint_radius * 0.5).rgb;
					sum += t;
					sq += t * t;
				}
			}
			vec3 mu = sum / 9.0;
			vec3 va = abs(sq / 9.0 - mu * mu);
			float v = va.r + va.g + va.b;
			if (v < best_v) { best_v = v; best = mu; }
		}
		// ink contour from the luminance gradient of the flattened neighbourhood
		float lx = luma(texture(TEXTURE, UV + vec2(texel.x * 1.5, 0.0)).rgb) - luma(texture(TEXTURE, UV - vec2(texel.x * 1.5, 0.0)).rgb);
		float ly = luma(texture(TEXTURE, UV + vec2(0.0, texel.y * 1.5)).rgb) - luma(texture(TEXTURE, UV - vec2(0.0, texel.y * 1.5)).rgb);
		float edge = smoothstep(0.1, 0.36, length(vec2(lx, ly)));
		vec3 p = best;
		// painted sunlight (picks D are bright, saturated noon illustrations; the renders are a soft overcast):
		// open the exposure with a highlight shoulder, push saturation hardest in the mid-tones (foliage, flowers,
		// paint), sun-warm the lit side and keep shadows a clean cool blue instead of grey
		float pl = luma(p);
		p = p * sun_exposure / (1.0 + p * (sun_exposure - 1.0) * 0.55);
		pl = luma(p);
		float mid = 1.0 - abs(pl - 0.5) * 1.4;
		p = mix(vec3(pl), p, 1.25 + 0.3 * clamp(mid, 0.0, 1.0));
		p = mix(p, p * vec3(1.07, 1.01, 0.88) + vec3(0.03, 0.02, 0.0), smoothstep(0.45, 0.95, pl) * 0.7);
		p = mix(p, p * vec3(0.9, 0.97, 1.12) + vec3(0.0, 0.01, 0.03), (1.0 - smoothstep(0.05, 0.35, pl)) * 0.6);
		p = max(p, vec3(0.035, 0.04, 0.06) + p * 0.9);
		p *= 1.0 - edge * ink * (0.25 + 0.55 * (1.0 - pl));
		// canvas grain: a fine, stable tooth (screen-space so it never swims with the picture)
		float g = hash(floor(FRAGCOORD.xy * 0.5)) - 0.5;
		p += g * 0.025;
		day = mix(day, clamp(p, 0.0, 1.0), paint);
	}
	vec3 c = world_at(day, UV);
	// bloom: thresholded highlights from a 12-tap ring at two radii
	vec3 glow = vec3(0.0);
	for (int i = 0; i < 6; i++) {
		float a = float(i) * 1.0472;
		vec2 o = vec2(cos(a), sin(a)) * texel;
		glow += max(world_at(texture(TEXTURE, UV + o * 5.0).rgb, UV + o * 5.0) - 0.8, 0.0);
		glow += max(world_at(texture(TEXTURE, UV + o * 12.0).rgb, UV + o * 12.0) - 0.8, 0.0) * 0.6;
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
