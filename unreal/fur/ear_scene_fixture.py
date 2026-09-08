"""Private world-space backdrop and bounded camera sequence for ear diagnosis."""
import inspect
import json
import textwrap
import numpy as np

def install(vp, out, background):
    from OpenGL import GL as gl
    from OpenGL.GL.shaders import compileProgram
    state = {'frames': [], 'background': background}
    clip_planes=vp._perspective_clip_planes
    def fixture_clip_planes(*args):
        near,far=clip_planes(*args)
        return near,max(far,100.0)
    vp._perspective_clip_planes=fixture_clip_planes

    def draw(self, mvp, previous_mvp):
        assert self._native_raster_active, 'Fixture requires native raster'
        if not background:
            return
        if 'program' not in state:
            vs = '''#version 330 core
layout(location=0) in vec3 position;
uniform mat4 currentMVP, previousMVP;
out vec4 previousClip;
void main(){gl_Position=currentMVP*vec4(position,1);previousClip=previousMVP*vec4(position,1);}
'''
            fs = '''#version 330 core
in vec4 previousClip;
uniform vec2 dimensions;
layout(location=0) out vec4 color;
layout(location=1) out vec4 bright;
layout(location=2) out vec4 depth;
layout(location=3) out vec2 velocity;
layout(location=4) out uint category;
void main(){
color=vec4(0,0,0,1);bright=vec4(0);
depth=vec4(0,0,0,1.0/gl_FragCoord.w);
vec2 previousUV=vec2(.5,-.5)*previousClip.xy/previousClip.w+.5;
velocity=gl_FragCoord.xy-previousUV*dimensions;category=0u;
}
'''
            state['program'] = compileProgram(self._compile_viewport_shader(vs, gl.GL_VERTEX_SHADER),
                                               self._compile_viewport_shader(fs, gl.GL_FRAGMENT_SHADER))
            # Fixed world-space plane; never follows the moving camera.
            eye = np.asarray(self.camera.eye_position(), dtype=np.float32)
            view = self.camera.view_matrix()
            right, up, forward = view[0,:3], view[1,:3], -view[2,:3]
            center = eye + forward * (self.camera.dist + 2.0)
            corners = [center + 10 * (x * right + y * up) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
            vertices = np.asarray([corners[i] for i in [0,1,2,0,2,3]], dtype=np.float32)
            state['plane_vertices'] = vertices.tolist()
            state['vao'] = gl.glGenVertexArrays(1)
            state['vbo'] = gl.glGenBuffers(1)
            gl.glBindVertexArray(state['vao']);gl.glBindBuffer(gl.GL_ARRAY_BUFFER,state['vbo'])
            gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STATIC_DRAW)
            gl.glEnableVertexAttribArray(0);gl.glVertexAttribPointer(0,3,gl.GL_FLOAT,False,12,None)
        blend, cull = gl.glIsEnabled(gl.GL_BLEND), gl.glIsEnabled(gl.GL_CULL_FACE)
        gl.glDisable(gl.GL_BLEND);gl.glDisable(gl.GL_CULL_FACE)
        gl.glDrawBuffers(5,[gl.GL_COLOR_ATTACHMENT0+i for i in range(5)])
        gl.glUseProgram(state['program'])
        vp._set_uniform_mat4(state['program'],'currentMVP',mvp)
        vp._set_uniform_mat4(state['program'],'previousMVP',previous_mvp)
        vp._set_uniform_2f(state['program'],'dimensions',*self._framebuffer_size())
        gl.glBindVertexArray(state['vao']);gl.glDrawArrays(gl.GL_TRIANGLES,0,6);gl.glBindVertexArray(0)
        if len(state.setdefault('background_probes',[])) < 3 and np.max(np.abs(mvp-previous_mvp)) > .001:
            saved_read=int(gl.glGetIntegerv(gl.GL_READ_BUFFER))
            gl.glReadBuffer(gl.GL_COLOR_ATTACHMENT2)
            depth=np.frombuffer(gl.glReadPixels(50,50,1,1,gl.GL_RGBA,gl.GL_FLOAT),dtype=np.float32).copy()
            gl.glReadBuffer(gl.GL_COLOR_ATTACHMENT3)
            velocity=np.frombuffer(gl.glReadPixels(50,50,1,1,gl.GL_RGBA,gl.GL_FLOAT),dtype=np.float32).copy()[:2]
            gl.glReadBuffer(saved_read)
            state['background_probes'].append({'linear_depth':float(depth[3]),'velocity':velocity.tolist()})
        if blend:gl.glEnable(gl.GL_BLEND)
        if cull:gl.glEnable(gl.GL_CULL_FACE)

    vp._draw_ear_background = draw
    source = textwrap.dedent(inspect.getsource(vp.Viewport3D.paintGL))
    marker = '    # Draw meshes\n'
    assert source.count(marker) == 1
    source = source.replace(marker, '    _draw_ear_background(self, mvp, previous_mvp)\n'+marker)
    namespace = {}
    exec(compile(source, '<ear-background-paint>', 'exec'), vars(vp), namespace)
    vp.Viewport3D.paintGL = namespace['paintGL']
    original = vp.Viewport3D.grabFramebuffer

    def grab(self):
        captured = original(self)
        if state.get('capturing') or state.get('done'):
            return captured
        state['capturing'] = True
        sequence = out/'sequence';sequence.mkdir(exist_ok=True)
        initial_yaw = float(self.camera.yaw)
        # Same phase schedule in backdrop/control runs: 12 moving, 12 held.
        for index in range(24):
            if index < 12:self.camera.yaw = initial_yaw + .15 * (index+1)
            frame = original(self)
            path = sequence/f'{index:02d}.png'
            assert not frame.isNull() and frame.save(str(path))
            state['frames'].append({'file':str(path),'yaw':float(self.camera.yaw),
                                    'temporal_age':int(self._temporal_sample_count),
                                    'phase':'moving' if index < 12 else 'held'})
        state['done'] = True
        if background:
            probes=state.get('background_probes',[])
            if len(probes)!=3 or not all(p['linear_depth']>0 for p in probes):
                raise RuntimeError('Backdrop depth readback failed')
        (out/'sequence.json').write_text(json.dumps({k:v for k,v in state.items()
            if k in ('frames','background','plane_vertices','background_probes')},indent=2))
        return captured

    vp.Viewport3D.grabFramebuffer = grab
