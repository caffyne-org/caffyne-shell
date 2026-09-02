# ---------------------------------------------------------------------------
# Shared GLSL for the reveal widgets
# ---------------------------------------------------------------------------
#
# The builtin fragment shaders below are the same animation the bundled
# "default" animation pack ships as applet_reveal.frag and dash_reveal.frag.
# They are what runs when no pack is active, so the two must stay in step --
# a pack shader replaces the whole fragment source, uniforms and all, and is
# compiled exactly as written.
#
# The uniform contract a pack shader is written against:
#
#   in  vec2      uv            0..1 across the widget, y up
#   out vec4      fragColor     premultiplied
#   sampler2D     u_texture     the child, drawn by cairo (y down)
#   float         u_time        0..1, raw elapsed / duration
#   int           u_opening     1 while opening, 0 while closing
#   int           u_direction   AppletReveal only: 0 anchors top, 1 anchors bottom
#   float         u_bx1 u_by1 u_bx2 u_by2   the easing control points
#   vec2          u_resolution  device pixels, set when the shader declares it
#
# How far the child scales from, and anything else about the shape of the
# motion, is the shader's own business -- a constant in the source rather
# than a uniform the widget passes in.
# ---------------------------------------------------------------------------

VERT_SRC = """#version 320 es
out vec2 uv;
void main() {
    // Explicit casts: ES will not implicitly widen the int to a float.
    vec2 pos = vec2(float(gl_VertexID & 1) * 2.0 - 1.0,
                    float(gl_VertexID >> 1) * 2.0 - 1.0);
    uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

# Cubic bezier easing via Newton-Raphson, shared by both fragment shaders.
#
# ``ease`` evaluates the curve forward and flips the result to close, rather
# than walking it backwards. The two agree at the ends and differ in the
# middle: the flip keeps the ease-out snap at the start of a close, which is
# the half of the animation you actually watch.
BEZIER_GLSL = """
float _bezier_x(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * bx1
         + 3.0 * mt * t  * t * bx2
         + t * t * t;
}
float _bezier_y(float t, float by1, float by2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * by1
         + 3.0 * mt * t  * t * by2
         + t * t * t;
}
float _bezier_dx(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * (mt * mt * bx1
                + 2.0 * mt * t * (bx2 - bx1)
                + t * t * (1.0 - bx2));
}
float cubic_bezier(float x, float bx1, float by1, float bx2, float by2) {
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;
    float t = x;
    for (int i = 0; i < 8; i++) {
        float fx  = _bezier_x(t, bx1, bx2) - x;
        float dfx = _bezier_dx(t, bx1, bx2);
        if (abs(dfx) < 1e-6) break;
        t -= fx / dfx;
        t  = clamp(t, 0.0, 1.0);
    }
    return _bezier_y(t, by1, by2);
}
float ease(float t, int opening, float bx1, float by1, float bx2, float by2) {
    float eased = cubic_bezier(clamp(t, 0.0, 1.0), bx1, by1, bx2, by2);
    return (opening == 1) ? eased : 1.0 - eased;
}
"""


def _with_bezier(src: str) -> str:
    return src.replace("{bezier}", BEZIER_GLSL)


# Scale from an edge anchor, fading in. Used by applets and notifications,
# which grow out of the bar they hang from.
APPLET_FRAG_SRC = _with_bezier("""#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_texture;
uniform float     u_time;
uniform int       u_opening;
uniform int       u_direction;   // 0 = down (anchor top), 1 = up (anchor bottom)
uniform float     u_bx1;
uniform float     u_by1;
uniform float     u_bx2;
uniform float     u_by2;

{bezier}

void main() {
    float progress = ease(u_time, u_opening, u_bx1, u_by1, u_bx2, u_by2);
    float scale    = mix(0.6, 1.0, progress);

    // The cairo surface is stored top-left origin; convert uv to match.
    vec2  tex_uv = vec2(uv.x, 1.0 - uv.y);
    vec2  anchor = vec2(0.5, (u_direction == 0) ? 0.0 : 1.0);
    vec2  scaled = (tex_uv - anchor) / scale + anchor;

    if (scaled.x < 0.0 || scaled.x > 1.0 ||
        scaled.y < 0.0 || scaled.y > 1.0) {
        discard;
    }

    fragColor = texture(u_texture, clamp(scaled, 0.0, 1.0)) * progress;
}
""")

# Scale from the centre with the colour channels pulled apart along the
# radius, the split closing as the reveal settles.
DASH_FRAG_SRC = _with_bezier("""#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_texture;
uniform float     u_time;
uniform int       u_opening;
uniform float     u_bx1;
uniform float     u_by1;
uniform float     u_bx2;
uniform float     u_by2;

{bezier}

float inside(vec2 p) {
    return step(0.0, p.x) * step(p.x, 1.0) * step(0.0, p.y) * step(p.y, 1.0);
}

void main() {
    float progress = ease(u_time, u_opening, u_bx1, u_by1, u_bx2, u_by2);
    float scale    = mix(0.8, 1.0, progress);

    vec2 centered = vec2(uv.x, 1.0 - uv.y) - 0.5;
    vec2 scaled   = centered / scale + 0.5;

    if (scaled.x < 0.0 || scaled.x > 1.0 ||
        scaled.y < 0.0 || scaled.y > 1.0) {
        discard;
    }

    float split = (1.0 - progress) * 0.025;
    vec2  dir   = normalize(centered + vec2(1e-4));

    vec2 uv_r = scaled + dir * split;
    vec2 uv_b = scaled - dir * split;

    // Masked rather than clamped: a channel that has been pushed off the
    // texture should vanish, not smear the edge texel across the gap.
    float r = texture(u_texture, clamp(uv_r, 0.0, 1.0)).r * inside(uv_r);
    float g = texture(u_texture, scaled).g;
    float b = texture(u_texture, clamp(uv_b, 0.0, 1.0)).b * inside(uv_b);
    float a = texture(u_texture, scaled).a;

    fragColor = vec4(r, g, b, a) * progress;
}
""")
