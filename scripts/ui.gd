class_name UI
## Small helpers for building the game's UI in code, styled after the Chief Auto art.

const GOLD := Color("e8b64c")
const GOLD_DIM := Color("8a6a2a")
const NAVY := Color(0.035, 0.045, 0.06, 0.88)
const NAVY_SOLID := Color("0b0e13")
const PANEL_LIGHT := Color(0.09, 0.11, 0.14, 0.92)
const GLASS_EDGE := Color(0.9, 0.74, 0.42, 0.55)
const CYAN := Color("5ad1ff")
## reference-style dialogue/showroom navy: translucent body, lighter desaturated header strip, light-blue rim
const DIALOG_NAVY := Color(0.04, 0.09, 0.2, 0.72)
const DIALOG_HEAD := Color(0.32, 0.45, 0.62, 0.85)
const DIALOG_RIM := Color(0.62, 0.8, 1.0, 0.75)

static var _body_font: Font
static var _head_font: Font


static func head_font() -> Font:
	if _head_font == null:
		var f: FontFile = load("res://assets/fonts/BarlowCondensed-SemiBold.woff2")
		f.fallbacks = [load("res://assets/fonts/DejaVuSans.ttf")]
		_head_font = f
	return _head_font
const TEXT := Color("f2f2f2")
const MUTED := Color("aab3c2")
const GOOD := Color("5fd17a")
const BAD := Color("ff6b5b")
const BLUE := Color("4aa3ff")


static func box(bg: Color, border: Color = Color.TRANSPARENT, radius := 10, border_w := 0, pad := 12) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(border_w)
	s.set_corner_radius_all(radius)
	s.content_margin_left = pad
	s.content_margin_right = pad
	s.content_margin_top = pad * 0.6
	s.content_margin_bottom = pad * 0.6
	return s


static func make_theme() -> Theme:
	var t := Theme.new()
	t.default_font_size = 18
	# Default font plus a fallback that has stars, arrows and check marks.
	var f: FontFile = load("res://assets/fonts/Barlow-Medium.woff2")
	f.fallbacks = [load("res://assets/fonts/DejaVuSans.ttf")]
	_body_font = f
	t.default_font = f
	t.set_color("font_color", "Label", TEXT)
	t.set_stylebox("normal", "Button", box(Color(0.07, 0.085, 0.11, 0.92), Color(1, 1, 1, 0.16), 6, 1, 14))
	t.set_stylebox("hover", "Button", box(Color(0.11, 0.14, 0.18, 0.96), GOLD, 6, 1, 14))
	t.set_stylebox("pressed", "Button", box(Color(0.25, 0.19, 0.08, 0.98), GOLD, 6, 1, 14))
	t.set_stylebox("disabled", "Button", box(Color(0.06, 0.06, 0.07, 0.6), Color(1, 1, 1, 0.06), 6, 1, 14))
	t.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", GOLD)
	t.set_color("font_pressed_color", "Button", Color.WHITE)
	t.set_color("font_disabled_color", "Button", Color(0.5, 0.5, 0.5))
	t.set_stylebox("panel", "PanelContainer", box(Color(0.05, 0.06, 0.08, 0.78), Color(1, 0.85, 0.6, 0.35), 12, 1, 16))
	t.set_stylebox("panel", "Panel", box(NAVY, GLASS_EDGE, 6, 1, 16))
	t.set_stylebox("background", "ProgressBar", box(Color(1, 1, 1, 0.08), Color.TRANSPARENT, 2, 0, 0))
	t.set_stylebox("fill", "ProgressBar", box(GOLD, Color.TRANSPARENT, 2, 0, 0))
	var grab := box(GOLD, Color.TRANSPARENT, 2, 0, 0)
	var track := box(Color(1, 1, 1, 0.18), Color.TRANSPARENT, 2, 0, 0)
	track.content_margin_top = 3
	track.content_margin_bottom = 3
	t.set_stylebox("slider", "HSlider", track)
	t.set_stylebox("grabber_area", "HSlider", grab)
	t.set_stylebox("grabber_area_highlight", "HSlider", grab)
	t.set_stylebox("normal", "OptionButton", box(Color(0.1, 0.15, 0.25, 0.95), GOLD_DIM, 8, 1, 12))
	t.set_stylebox("hover", "OptionButton", box(Color(0.16, 0.22, 0.35, 0.98), GOLD, 8, 1, 12))
	t.set_stylebox("pressed", "OptionButton", box(Color(0.16, 0.22, 0.35, 0.98), GOLD, 8, 1, 12))
	t.set_stylebox("focus", "OptionButton", StyleBoxEmpty.new())
	for st in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
		t.set_stylebox(st, "CheckBox", box(Color(1, 1, 1, 0.06) if st != "hover" else Color(1, 1, 1, 0.12), Color(1, 1, 1, 0.15), 4, 1, 10))
	for c in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		t.set_color(c, "CheckBox", TEXT)
	t.set_stylebox("panel", "PopupMenu", box(NAVY_SOLID, GOLD_DIM, 8, 1, 8))
	t.set_font_size("font_size", "PopupMenu", 18)
	t.set_stylebox("normal", "LineEdit", box(Color(0.9, 0.92, 0.95), Color.TRANSPARENT, 14, 0, 12))
	t.set_stylebox("read_only", "LineEdit", box(Color(1, 1, 1), Color(0.75, 0.77, 0.82), 14, 1, 12))
	t.set_color("font_color", "LineEdit", Color(0.2, 0.2, 0.25))
	t.set_color("font_uneditable_color", "LineEdit", Color(0.3, 0.32, 0.38))
	t.set_stylebox("scroll", "VScrollBar", box(Color(0, 0, 0, 0.2), Color.TRANSPARENT, 4, 0, 0))
	t.set_stylebox("grabber", "VScrollBar", box(GOLD_DIM, Color.TRANSPARENT, 4, 0, 0))
	return t


static func label(text: String, size := 18, color := TEXT, bold := false, wrap := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if bold:
		l.add_theme_font_override("font", head_font())
		l.add_theme_font_size_override("font_size", size + 2)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


## A wrapping paragraph label.
static func para(text: String, size := 17, color := TEXT) -> Label:
	return label(text, size, color, false, true)


static func button(text: String, cb: Callable, min_w := 0, min_h := 48) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(min_w, min_h)
	b.pressed.connect(cb)
	return b


static func gold_button(text: String, cb: Callable, min_w := 0, min_h := 52) -> Button:
	var b := button(text, cb, min_w, min_h)
	var n := box(Color(0.78, 0.6, 0.26, 0.97), Color(1, 0.88, 0.6), 6, 1, 16)
	n.shadow_color = Color(0.9, 0.7, 0.3, 0.25)
	n.shadow_size = 6
	b.add_theme_stylebox_override("normal", n)
	b.add_theme_stylebox_override("hover", box(Color(0.9, 0.72, 0.35, 1.0), Color.WHITE, 6, 1, 16))
	b.add_theme_stylebox_override("pressed", box(Color(0.6, 0.45, 0.18, 1.0), Color.WHITE, 6, 1, 16))
	b.add_theme_color_override("font_color", Color("15110a"))
	b.add_theme_color_override("font_hover_color", Color("15110a"))
	b.add_theme_font_override("font", head_font())
	b.add_theme_font_size_override("font_size", 21)
	b.text = text.to_upper()
	return b


## Smoked glass with a warm rim, the one panel look used across the game.
const GLASS := Color(0.05, 0.06, 0.08, 0.78)
const GLASS_RIM := Color(1, 0.85, 0.6, 0.35)


static func panel(bg := GLASS, border := GLASS_RIM, pad := 16) -> PanelContainer:
	var p := PanelContainer.new()
	var radius := 6
	if bg.v < 0.3:
		# every dark panel shares the glass look; light panels (web pages, the whiteboard) keep their colours
		bg = Color(GLASS, max(bg.a, 0.72))
		if border == GOLD_DIM:
			border = GLASS_RIM
		radius = 12
	var sb := box(bg, border, radius, 1, pad)
	if bg.a < 0.99 and bg.v < 0.3:
		sb.shadow_color = Color(0, 0, 0, 0.45)
		sb.shadow_size = 10
	p.add_theme_stylebox_override("panel", sb)
	return p


## Uppercase condensed panel title with a gold underline, like the mockup headers.
static func header(text: String, size := 22) -> Control:
	var v := vbox(4)
	v.add_child(label(text.to_upper(), size, TEXT, true))
	v.add_child(rule(GOLD))
	return v


static func rule(c := Color(1, 1, 1, 0.15)) -> ColorRect:
	var r := ColorRect.new()
	r.color = c
	r.custom_minimum_size = Vector2(0, 1)
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return r


static func vbox(sep := 8) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func hbox(sep := 8) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", sep)
	return h


static func bar(value: float, max_value := 100.0, color := GOLD, height := 12) -> ProgressBar:
	var b := ProgressBar.new()
	b.max_value = max_value
	b.value = value
	b.show_percentage = false
	b.custom_minimum_size = Vector2(0, height)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.add_theme_stylebox_override("fill", box(color, Color.TRANSPARENT, 5, 0, 0))
	return b


static func cond_color(c: float) -> Color:
	if c >= 75:
		return GOOD
	if c >= 50:
		return GOLD
	return BAD


static func stars(rating: float) -> String:
	var full := int(floor(rating))
	var half := rating - full >= 0.5
	var s := ""
	for i in 5:
		if i < full:
			s += "★"
		elif i == full and half:
			s += "★"
		else:
			s += "☆"
	return s


static func spacer() -> Control:
	var c := Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return c


static func scroll(child: Control) -> ScrollContainer:
	var s := ScrollContainer.new()
	s.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	s.size_flags_vertical = Control.SIZE_EXPAND_FILL
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	child.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.add_child(child)
	return s


static func clear(node: Node) -> void:
	for c in node.get_children():
		node.remove_child(c)
		c.queue_free()
