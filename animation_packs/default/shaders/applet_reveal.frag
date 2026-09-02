#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_texture;
uniform float     u_time;        // raw 0..1 elapsed / duration
uniform int       u_opening;     // 1 = open, 0 = close
uniform int       u_direction;   // 0 = down (anchor top), 1 = up (anchor bottom)

// --- cubic bezier easing via Newton-Raphson ---
// Control points: (0,0) .. (cx1,cy1) .. (cx2,cy2) .. (1,1)
uniform float u_bx1;
uniform float u_by1;
uniform float u_bx2;
uniform float u_by2;

float bezier_x(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * bx1
         + 3.0 * mt * t  * t * bx2
         + t * t * t;
}

float bezier_y(float t, float by1, float by2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * by1
         + 3.0 * mt * t  * t * by2
         + t * t * t;
}

float bezier_dx(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * (mt * mt * bx1
                + 2.0 * mt * t * (bx2 - bx1)
                + t * t * (1.0 - bx2));
}

// Solve bezier_x(t) = x via Newton-Raphson, return eased y
float cubic_bezier(float x, float bx1, float by1, float bx2, float by2) {
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;

    float t = x; // initial guess
    for (int i = 0; i < 8; i++) {
        float fx  = bezier_x(t, bx1, bx2) - x;
        float dfx = bezier_dx(t, bx1, bx2);
        if (abs(dfx) < 1e-6) break;
        t -= fx / dfx;
        t  = clamp(t, 0.0, 1.0);
    }
    return bezier_y(t, by1, by2);
}

void main() {
    float raw_t = clamp(u_time, 0.0, 1.0);
    float eased;

    if (u_opening == 1) {
        eased = cubic_bezier(raw_t, u_bx1, u_by1, u_bx2, u_by2);
    } else {
        // Evaluate forward, flip — preserves the snappy ease-out feel on close
        eased = 1.0 - cubic_bezier(raw_t, u_bx1, u_by1, u_bx2, u_by2);
    }

    float scale = mix(0.6, 1.0, eased);

    // Cairo surface is stored top-left origin; convert uv to match
    vec2 tex_uv = vec2(uv.x, 1.0 - uv.y);

    // Anchor point: top-centre for "down", bottom-centre for "up"
    float anchor_y = (u_direction == 0) ? 0.0 : 1.0;
    vec2 anchor = vec2(0.5, anchor_y);

    // Inverse-scale the UV around the anchor to get the source texel
    vec2 scaled = (tex_uv - anchor) / scale + anchor;

    if (scaled.x < 0.0 || scaled.x > 1.0 ||
        scaled.y < 0.0 || scaled.y > 1.0) {
        discard;
    }

    vec4 color = texture(u_texture, clamp(scaled, 0.0, 1.0));
    fragColor = color * eased;
}
