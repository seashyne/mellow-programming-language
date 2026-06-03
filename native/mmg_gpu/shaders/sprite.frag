#version 120
varying vec2 v_uv;
varying vec4 v_color;
uniform sampler2D u_tex;
void main() {
    vec4 texel = texture2D(u_tex, v_uv);
    gl_FragColor = texel * v_color;
}
