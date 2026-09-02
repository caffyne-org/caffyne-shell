#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_texture;
uniform float     u_time;
uniform int       u_opening;

uniform float u_bx1;
uniform float u_by1;
uniform float u_bx2;
uniform float u_by2;

float bezier_x(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * bx1 + 3.0 * mt * t * t * bx2 + t * t * t;
}

float bezier_y(float t, float by1, float by2) {
    float mt = 1.0 - t;
    return 3.0 * mt * mt * t * by1 + 3.0 * mt * t * t * by2 + t * t * t;
}

float bezier_dx(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0 * (mt * mt * bx1 + 2.0 * mt * t * (bx2 - bx1) + t * t * (1.0 - bx2));
}

float cubic_bezier(float x, float bx1, float by1, float bx2, float by2) {
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;

    float t = x;
    for (int i = 0; i < 4; i++) {
        float fx  = bezier_x(t, bx1, bx2) - x;
        float dfx = bezier_dx(t, bx1, bx2);
        if (abs(dfx) < 1e-4) break;
        t -= fx / dfx;
        t  = clamp(t, 0.0, 1.0);
    }
    return bezier_y(t, by1, by2);
}

void main() {
    float raw_t = clamp(u_time, 0.0, 1.0);
    float progress = cubic_bezier(raw_t, u_bx1, u_by1, u_bx2, u_by2);
    if (u_opening == 0) {
        progress = 1.0 - progress;
    }

    float scale = mix(0.8, 1.0, progress);
    
    vec2 flipped_uv = vec2(uv.x, 1.0 - uv.y);
    vec2 centered = flipped_uv - 0.5;
    vec2 scaled = centered / scale + 0.5;

    if (scaled.x < 0.0 || scaled.x > 1.0 || scaled.y < 0.0 || scaled.y > 1.0) {
        discard;
    }

    float velocity = sin(raw_t * 3.14159265);
    vec2 dir = normalize(centered + vec2(1e-4));
    float split_amount = (1.0 - progress) * 0.025;

    vec2 uv_r = scaled + dir * split_amount;
    vec2 uv_g = scaled;
    vec2 uv_b = scaled - dir * split_amount;

    float mask_r = step(0.0, uv_r.x) * step(uv_r.x, 1.0) * step(0.0, uv_r.y) * step(uv_r.y, 1.0);
    float mask_b = step(0.0, uv_b.x) * step(uv_b.x, 1.0) * step(0.0, uv_b.y) * step(uv_b.y, 1.0);

    float r = texture(u_texture, clamp(uv_r, 0.0, 1.0)).r * mask_r;
    float g = texture(u_texture, uv_g).g;
    float b = texture(u_texture, clamp(uv_b, 0.0, 1.0)).b * mask_b;
    float a = texture(u_texture, scaled).a;

    fragColor = vec4(r, g, b, a) * progress;
}
