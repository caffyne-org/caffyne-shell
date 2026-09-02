#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_tex_from;
uniform sampler2D u_tex_to;
uniform float     u_time;
uniform float     u_bx1, u_by1, u_bx2, u_by2;

float bezier_x(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0*mt*mt*t*bx1 + 3.0*mt*t*t*bx2 + t*t*t;
}
float bezier_y(float t, float by1, float by2) {
    float mt = 1.0 - t;
    return 3.0*mt*mt*t*by1 + 3.0*mt*t*t*by2 + t*t*t;
}
float bezier_dx(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0*(mt*mt*bx1 + 2.0*mt*t*(bx2-bx1) + t*t*(1.0-bx2));
}
float cubic_bezier(float x, float bx1, float by1, float bx2, float by2) {
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;
    float t = x;
    for (int i = 0; i < 8; i++) {
        float fx  = bezier_x(t, bx1, bx2) - x;
        float dfx = bezier_dx(t, bx1, bx2);
        if (abs(dfx) < 1e-6) break;
        t -= fx / dfx;
        t  = clamp(t, 0.0, 1.0);
    }
    return bezier_y(t, by1, by2);
}

// simple hash for per-tile randomness
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
void main() {
    vec2 tex_uv = vec2(uv.x, 1.0 - uv.y);
    float t = cubic_bezier(clamp(u_time, 0.0, 1.0), u_bx1, u_by1, u_bx2, u_by2);

    float tiles   = 12.0;
    vec2  tile    = floor(tex_uv * tiles);
    vec2  tile_uv = fract(tex_uv * tiles);

    float delay   = hash(tile) * 0.4;
    float local_t = clamp((t - delay) / (1.0 - delay), 0.0, 1.0);

    float angle = local_t * 3.14159 * 0.5 * (hash(tile + 0.5) > 0.5 ? 1.0 : -1.0);
    float scale = 1.0 - local_t;

    vec2 center  = vec2(0.5);
    vec2 rotated = tile_uv - center;
    float s = sin(angle), c = cos(angle);
    rotated = vec2(rotated.x * c - rotated.y * s,
                   rotated.x * s + rotated.y * c);
    rotated = rotated / max(scale, 0.001) + center;

    vec4 from_col = vec4(0.0);
    if (scale > 0.01 && rotated.x >= 0.0 && rotated.x <= 1.0 &&
                        rotated.y >= 0.0 && rotated.y <= 1.0) {
        from_col = texture(u_tex_from, (tile + rotated) / tiles) * (1.0 - local_t);
    }

    float delay_to   = (1.0 - hash(tile + 99.0)) * 0.4;
    float local_t_to = clamp((t - delay_to) / (1.0 - delay_to), 0.0, 1.0);

    float angle_to = (1.0 - local_t_to) * 3.14159 * 0.5 * (hash(tile + 7.3) > 0.5 ? 1.0 : -1.0);
    float scale_to = local_t_to;

    vec2 rotated_to = tile_uv - center;
    float s2 = sin(angle_to), c2 = cos(angle_to);
    rotated_to = vec2(rotated_to.x * c2 - rotated_to.y * s2,
                      rotated_to.x * s2 + rotated_to.y * c2);
    rotated_to = rotated_to / max(scale_to, 0.001) + center;

    vec4 to_col = vec4(0.0);
    if (scale_to > 0.01 && rotated_to.x >= 0.0 && rotated_to.x <= 1.0 &&
                           rotated_to.y >= 0.0 && rotated_to.y <= 1.0) {
        to_col = texture(u_tex_to, (tile + rotated_to) / tiles) * local_t_to;
    }

    fragColor = from_col + to_col;
}
