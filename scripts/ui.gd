class_name UI
## Small helpers for building the game's UI in code, styled after the Chief Auto art.

const GOLD := Color("e8b64c")
const GOLD_DIM := Color("8a6a2a")
const NAVY := Color(0.05, 0.08, 0.14, 0.88)
const NAVY_SOLID := Color("0d1524")
const PANEL_LIGHT := Color(0.12, 0.17, 0.27, 0.92)
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
	var f: Font = ThemeDB.fallback_font.duplicate()
	f.fallbacks = [load("res://assets/fonts/DejaVuSans.ttf")]
	t.default_font = f
	t.set_color("font_color", "Label", TEXT)
	t.set_stylebox("normal", "Button", box(Color(0.1, 0.15, 0.25, 0.95), GOLD_DIM, 8, 1, 14))
	t.set_stylebox("hover", "Button", box(Color(0.16, 0.22, 0.35, 0.98), GOLD, 8, 2, 14))
	t.set_stylebox("pressed", "Button", box(Color(0.3, 0.24, 0.1, 0.98), GOLD, 8, 2, 14))
	t.set_stylebox("disabled", "Button", box(Color(0.1, 0.1, 0.12, 0.7), Color(0.3, 0.3, 0.3), 8, 1, 14))
	t.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", GOLD)
	t.set_color("font_pressed_color", "Button", Color.WHITE)
	t.set_color("font_disabled_color", "Button", Color(0.5, 0.5, 0.5))
	t.set_stylebox("panel", "PanelContainer", box(NAVY, GOLD_DIM, 12, 1, 16))
	t.set_stylebox("panel", "Panel", box(NAVY, GOLD_DIM, 12, 1, 16))
	t.set_stylebox("background", "ProgressBar", box(Color(0.15, 0.15, 0.2), Color.TRANSPARENT, 5, 0, 0))
	t.set_stylebox("fill", "ProgressBar", box(GOLD, Color.TRANSPARENT, 5, 0, 0))
	t.set_stylebox("normal", "OptionButton", box(Color(0.1, 0.15, 0.25, 0.95), GOLD_DIM, 8, 1, 12))
	t.set_stylebox("hover", "OptionButton", box(Color(0.16, 0.22, 0.35, 0.98), GOLD, 8, 1, 12))
	t.set_stylebox("pressed", "OptionButton", box(Color(0.16, 0.22, 0.35, 0.98), GOLD, 8, 1, 12))
	t.set_stylebox("focus", "OptionButton", StyleBoxEmpty.new())
	for st in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
		t.set_stylebox(st, "CheckBox", box(Color(1, 1, 1, 0.6), Color(0.6, 0.6, 0.65), 6, 1, 10))
	for c in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		t.set_color(c, "CheckBox", Color(0.12, 0.12, 0.16))
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
		l.add_theme_constant_override("outline_size", 1)
		l.add_theme_color_override("font_outline_color", color)
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
	b.add_theme_stylebox_override("normal", box(Color(0.55, 0.4, 0.1, 0.95), GOLD, 8, 2, 16))
	b.add_theme_stylebox_override("hover", box(Color(0.7, 0.52, 0.15, 0.98), Color.WHITE, 8, 2, 16))
	b.add_theme_font_size_override("font_size", 20)
	return b


static func panel(bg := NAVY, border := GOLD_DIM, pad := 16) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", box(bg, border, 12, 1, pad))
	return p


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
