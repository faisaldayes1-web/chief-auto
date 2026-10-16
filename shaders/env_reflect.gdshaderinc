// Hand-rolled image-based reflections from an equirect map (u = 0.5 looks down -z, u grows towards +x,
// v = 0 straight up). The web build has no sky radiance (WebGL can't filter the panorama), so glossy
// surfaces sample this instead. Rougher surfaces read a blurrier mip.
vec3 env_sample(sampler2D map, vec3 view_normal, vec3 view_dir, mat4 inv_view, float rough) {
	vec3 r = reflect(-view_dir, view_normal);
	vec3 w = normalize((inv_view * vec4(r, 0.0)).xyz);
	vec2 uv = vec2(atan(w.x, -w.z) / 6.2831853 + 0.5, acos(clamp(w.y, -1.0, 1.0)) / 3.1415927);
	return textureLod(map, uv, rough * 7.0).rgb;
}

float env_fresnel(vec3 n, vec3 v, float f0) {
	float c = 1.0 - clamp(dot(n, v), 0.0, 1.0);
	return f0 + (1.0 - f0) * c * c * c * c * c;
}
