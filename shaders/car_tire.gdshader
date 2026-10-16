// Tyre rubber with a tread you can see: circumferential grooves and angled sipes on the tread face,
// moulded rings on the sidewall. Worn tyres lose their tread and go grey and shiny.
// center/axis come from the wheel mesh's bounds (object space), so it works on every car model.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec3 center = vec3(0.0);
uniform vec3 axis = vec3(1.0, 0.0, 0.0);
uniform float half_width = 0.11;
uniform float radius = 0.33;
uniform float wear = 0.0;
uniform vec3 glow = vec3(0.0);

varying vec3 op;
varying vec3 on;

void vertex() {
	op = VERTEX - center;
	on = NORMAL;
}

void fragment() {
	float ax = dot(op, axis);
	vec3 rad = op - axis * ax;
	float r = length(rad);
	// angle around the axle, from two directions perpendicular to it
	vec3 u = normalize(abs(axis.y) < 0.9 ? cross(axis, vec3(0.0, 1.0, 0.0)) : cross(axis, vec3(1.0, 0.0, 0.0)));
	vec3 v = cross(axis, u);
	float ang = atan(dot(rad, v), dot(rad, u));
	float side = abs(dot(normalize(on), axis));   // 1 on the sidewall, 0 on the tread face
	float t = ax / max(half_width, 0.01);          // -1..1 across the tread

	vec3 col = vec3(0.028);
	float rough = 0.88;
	float depth = 1.0 - wear;
	// tread face: two deep circumferential grooves plus angled sipes between them
	float tread = 1.0 - smoothstep(0.35, 0.6, side);
	float grooves = 1.0 - smoothstep(0.035, 0.07, min(abs(t - 0.38), abs(t + 0.38)));
	float sipe_p = fract(ang * 9.549 * 6.0 + abs(t) * 2.2);   // 6 sipes per radian, chevron across the centre
	float sipes = (1.0 - smoothstep(0.05, 0.14, abs(sipe_p - 0.5))) * step(0.12, abs(t)) * (1.0 - step(0.9, abs(t)));
	float cut = max(grooves, sipes * 0.85) * tread * depth;
	col *= 1.0 - cut * 0.75;
	// sidewall: a smooth band with moulded rings near the rim and a raised shoulder near the tread
	float rn = r / max(radius, 0.01);
	float ring = (1.0 - smoothstep(0.0, 0.01, abs(rn - 0.8))) + (1.0 - smoothstep(0.0, 0.01, abs(rn - 0.85))) * 0.6;
	col += vec3(0.02) * ring * side;
	rough = mix(rough, 0.6, side * 0.4);
	// bald rubber: grey and shiny
	col = mix(col, vec3(0.13), wear * 0.85);
	rough = mix(rough, 0.5, wear);
	ALBEDO = col;
	ROUGHNESS = rough;
	METALLIC = 0.0;
	SPECULAR = 0.35;
	EMISSION = glow;
}
