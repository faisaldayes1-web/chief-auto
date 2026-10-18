class_name RenderQuality
extends RefCounted
## Shared 3D quality presets. Desktop builds run Forward+ (project.godot override),
## web/mobile stay on gl_compatibility. Call from any 3D view:
##   RenderQuality.apply_environment(env, viewport_or_world_node, sun)
## `world_node` may be a SubViewport/Viewport (AA settings applied) or any Node
## inside one (a ReflectionProbe is added under it on Forward+).

static func is_forward_plus() -> bool:
	# Godot 4.3 has no get_current_rendering_method(); the compatibility
	# renderer has no RenderingDevice, so use that plus the effective setting.
	if RenderingServer.get_rendering_device() == null:
		return false
	var args := OS.get_cmdline_args()
	var i := args.find("--rendering-method")
	if i >= 0 and i + 1 < args.size():
		return args[i + 1] == "forward_plus"
	return str(ProjectSettings.get_setting_with_override("rendering/renderer/rendering_method")) == "forward_plus"

static func apply_environment(env: Environment, world_node: Node = null, sun: DirectionalLight3D = null, probe_size := Vector3(16, 6, 12)) -> void:
	if env == null:
		return
	if is_forward_plus():
		env.tonemap_mode = Environment.TONE_MAPPER_ACES
		env.tonemap_exposure = 0.95
		env.tonemap_white = 6.0
		env.ssao_enabled = true
		env.ssao_radius = 0.9
		env.ssao_intensity = 1.6
		env.ssao_detail = 0.6
		env.ssil_enabled = true
		env.ssil_radius = 2.5
		env.ssil_intensity = 0.8
		env.ssr_enabled = true
		env.ssr_max_steps = 64
		env.ssr_fade_in = 0.15
		env.ssr_depth_tolerance = 0.3
		env.glow_enabled = true
		env.glow_intensity = 0.35
		env.glow_bloom = 0.04
		env.glow_hdr_threshold = 1.2
		env.adjustment_enabled = true
		env.adjustment_contrast = 1.05
		env.adjustment_saturation = 1.05
		# SDFGI is left off: small isolated sets with transparent backgrounds gain
		# little and it costs a lot; SSIL + reflection probe gives the bounce look.
		if sun:
			sun.shadow_blur = 1.5
			sun.light_angular_distance = 1.2   # PCSS soft shadows
			sun.shadow_bias = 0.03
			sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
		RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_HIGH)
		RenderingServer.positional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_MEDIUM)
		if world_node:
			var vp: Viewport = world_node if world_node is Viewport else world_node.get_viewport()
			if vp:
				# Godot 4.3: TAA and SSR overwrite the alpha of a transparent viewport, so the garage car view
				# (drawn over the 2D garage photo) came out as a black box. Such views keep MSAA + FXAA, the
				# reflection probe and the sky reflections, without those two.
				var see_through := vp.transparent_bg
				vp.use_taa = not see_through
				vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
				if see_through:
					env.ssr_enabled = false
			if world_node.get_node_or_null("RQProbe") == null:
				var p := ReflectionProbe.new()
				p.name = "RQProbe"
				p.size = probe_size
				p.position = Vector3(0, probe_size.y * 0.5 - 0.5, 0)
				p.update_mode = ReflectionProbe.UPDATE_ONCE
				p.box_projection = true
				p.enable_shadows = true
				p.intensity = 0.8
				world_node.add_child(p)
	else:
		# compatibility (web): keep the light setup; only cheap tweaks
		env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
		env.glow_enabled = false
		if sun:
			sun.shadow_blur = 1.0
