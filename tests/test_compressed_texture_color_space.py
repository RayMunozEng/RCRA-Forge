"""Texture format regressions: no GL context or graphics process needed."""
import pytest
from ui.viewport import _compressed_gl_format

@pytest.mark.parametrize('linear,srgb,gl_linear,gl_srgb',[
 (71,72,0x83F1,0x8C4D),(74,75,0x83F2,0x8C4E),
 (77,78,0x83F3,0x8C4F),(98,99,0x8E8C,0x8E8D)])
def test_explicit_srgb_format_survives_data_role(linear,srgb,gl_linear,gl_srgb):
 # Typed source SRGB must agree with D3D decoding even for specular maps.
 assert _compressed_gl_format(srgb,False)==gl_srgb
 assert _compressed_gl_format(srgb,True)==gl_srgb
 assert _compressed_gl_format(linear,False)==gl_linear
 assert _compressed_gl_format(linear,True)==gl_srgb

from types import SimpleNamespace
import ui.viewport as viewport

@pytest.fixture
def upload_recorder(monkeypatch):
    calls=[]
    for name in ('glBindTexture','glTexParameteri','glTexParameterf','glGenerateMipmap','glDeleteTextures'):
        monkeypatch.setattr(viewport,name,lambda *args:None)
    monkeypatch.setattr(viewport,'glGenTextures',lambda count:7)
    monkeypatch.setattr(viewport,'glTexImage2D',lambda *args:calls.append(('decoded',args[2])))
    monkeypatch.setattr(viewport,'glCompressedTexImage2D',lambda *args:calls.append(('compressed',args[2])))
    state=SimpleNamespace(_max_texture_anisotropy=1,_uploaded_texture_signatures={},_gpu_meshes=[])
    return state,calls

@pytest.mark.parametrize('fmt,expected',[(29,0x8C43),(72,0x8C43),(75,0x8C43),(78,0x8C43),(91,0x8C43),(93,0x8C43),(99,0x8C43),(28,0x8058),(71,0x8058),(98,0x8058),(None,0x8058)])
def test_decoded_response_upload_preserves_source_color_space(upload_recorder,fmt,expected):
    state,calls=upload_recorder
    slot=(bytes([128,96,32,255])*16,4,4,'response',{'dxgi_format':fmt})
    viewport.Viewport3D._upload_textures(state,{0:{'specular_color':slot}})
    assert calls==[('decoded',expected)]

@pytest.mark.parametrize('mips', [True,False])
def test_sheep_compressed_response_upload_is_srgb(upload_recorder,mips):
    state,calls=upload_recorder
    meta={'dxgi_format':72}
    meta['compressed_mips' if mips else 'compressed_mip0']=[(4,4,bytes(8))] if mips else bytes([1])*8
    slot=(bytes([128,96,32,255])*16,4,4,'response',meta)
    viewport.Viewport3D._upload_textures(state,{0:{'specular_color':slot}})
    assert calls==[('compressed',0x8C4D)]

def test_same_pixels_reupload_when_source_color_space_changes(upload_recorder):
    state,calls=upload_recorder
    pixels=bytes([128,96,32,255])*16
    for fmt in (28,28,29):
        slot=(pixels,4,4,'response',{'dxgi_format':fmt})
        viewport.Viewport3D._upload_textures(state,{0:{'specular_color':slot}})
    assert calls==[('decoded',0x8058),('decoded',0x8C43)]

@pytest.mark.parametrize('role,fmt,expected',[
 ('base_color',None,0x8C43),('base_color',71,0x8C43),
 ('fur_control',71,0x8058),('normal',28,0x8058),('specular_color',99,0x8C43)])
def test_upload_keeps_existing_color_and_linear_control_policy(upload_recorder,role,fmt,expected):
    state,calls=upload_recorder
    slot=(bytes([128,96,32,255])*16,4,4,'map',{'dxgi_format':fmt})
    viewport.Viewport3D._upload_textures(state,{0:{role:slot}})
    assert calls==[('decoded',expected)]
