/* Original two-pass fog shader. No game assets or copied Balatro shader code. */
(()=>{
 const canvas=document.getElementById('landingShader'),button=document.getElementById('backgroundMotion'),backdrop=document.getElementById('landingBackdrop');
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let paused=reduced.matches,chosen=false,gl=null,resources=null,raf=0,last=0,time=0,frames=0,lost=false;
 const vertex=`attribute vec2 a_position; varying vec2 uv;
 void main(){uv=a_position*.5+.5;gl_Position=vec4(a_position,0.,1.);}`;
 const field=`varying vec2 uv; uniform float u_time; uniform float u_aspect;
 float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
 float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
 float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<4;i++){v+=a*noise(p);p=mat2(.8,.6,-.6,.8)*p*2.03+3.7;a*=.5;}return v;}
 mat2 rotate(float a){return mat2(cos(a),-sin(a),sin(a),cos(a));}
 void main(){
  vec2 p=(uv-.5)*vec2(u_aspect,1.)*3.;float t=u_time*.055;
  // Rotate the coordinate field more near the centre, then warp at two scales.
  p=rotate(.65/(.35+length(p))+t*.12)*p;
  vec2 q=vec2(fbm(p+t*.27),fbm(p+vec2(4.2,1.7)-t*.19));
  vec2 r=vec2(fbm(p+2.8*q+vec2(1.7,9.2)+t*.21),fbm(p+2.8*q+vec2(8.3,2.8)-t*.16));
  float f=fbm(p+3.3*r);float folds=sin((p.x*.65+p.y*.4+f*2.6)*5.2-t*.6)*.5+.5;
  float mist=smoothstep(.25,.83,f*.68+folds*.32);
  vec3 dark=vec3(.075,.09,.082),fog=vec3(.32,.43,.36),light=vec3(.65,.69,.66);
  vec3 color=mix(dark,fog,mist);color=mix(color,light,pow(mist,3.)*.42);
  gl_FragColor=vec4(color,1.);
 }`;
 const composite=`varying vec2 uv;uniform sampler2D u_fog;uniform vec2 u_size;uniform float u_time;
 void main(){
  vec3 color=texture2D(u_fog,uv).rgb;
  float vignette=smoothstep(.08,.75,length((uv-.5)*vec2(1.,.85)));
  color*=1.-.48*vignette;
  // Fine film grain is a separate full-resolution layer, independent of fog resolution.
  float grain=fract(sin(dot(floor(uv*u_size)+floor(u_time*8.),vec2(12.9898,78.233)))*43758.5453)-.5;
  color+=grain*.018;
  gl_FragColor=vec4(color,1.);
 }`;
 function controls(){button.disabled=false;button.textContent=paused?'▶':'Ⅱ';button.setAttribute('aria-pressed',String(paused));button.title=button.ariaLabel=paused?'播放背景动画':'暂停背景动画'}
 function stop(){cancelAnimationFrame(raf);raf=0;last=0}
 function release(){if(!gl||!resources)return;const r=resources;gl.deleteProgram(r.fog?.program);gl.deleteProgram(r.composite?.program);gl.deleteBuffer(r.buffer);gl.deleteTexture(r.texture);gl.deleteFramebuffer(r.target);resources=null}
 function fallback(reason='WebGL unavailable'){stop();release();canvas.dataset.renderer='fallback';canvas.dataset.fallbackReason=reason;backdrop.dataset.renderer='fallback';canvas.style.opacity='0';controls();sync()}
 function program(source){
  const precision=gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER,gl.HIGH_FLOAT).precision?'highp':'mediump';
  const shaders=[];let result=null;
  try{
   for(const [type,code]of [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,'precision '+precision+' float;\n'+source]]){
    const shader=gl.createShader(type);shaders.push(shader);gl.shaderSource(shader,code);gl.compileShader(shader);
    if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error('Shader compile failed');
   }
   result=gl.createProgram();shaders.forEach(shader=>gl.attachShader(result,shader));gl.linkProgram(result);
   if(!gl.getProgramParameter(result,gl.LINK_STATUS))throw Error('Shader link failed');
   return {program:result,position:gl.getAttribLocation(result,'a_position'),time:gl.getUniformLocation(result,'u_time'),aspect:gl.getUniformLocation(result,'u_aspect'),size:gl.getUniformLocation(result,'u_size'),fog:gl.getUniformLocation(result,'u_fog')};
  }catch(error){if(result)gl.deleteProgram(result);throw error}finally{shaders.forEach(shader=>gl.deleteShader(shader))}
 }
 function initialize(){
  try{
   gl=canvas.getContext('webgl',{alpha:false,antialias:false,depth:false,stencil:false,powerPreference:'low-power'});
   if(!gl)return fallback('WebGL context unavailable');
   resources={fog:null,composite:null,buffer:null,texture:null,target:null};
   resources.fog=program(field);resources.composite=program(composite);
   resources.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,resources.buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
   resources.texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,resources.texture);
   for(const parameter of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.LINEAR);
   for(const parameter of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.CLAMP_TO_EDGE);
   resources.target=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,resources.target);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,resources.texture,0);
   canvas.dataset.renderer=backdrop.dataset.renderer='webgl';delete canvas.dataset.fallbackReason;canvas.style.opacity='1';resize();controls();sync();
  }catch(error){fallback(error.message)}
 }
 function resize(){
  if(!resources||lost)return;
  const scale=Math.min(devicePixelRatio||1,1.5,1280/Math.max(innerWidth,innerHeight));
  canvas.width=Math.max(1,Math.round(innerWidth*scale));canvas.height=Math.max(1,Math.round(innerHeight*scale));
  const r=resources;r.width=Math.max(1,Math.round(canvas.width*.6));r.height=Math.max(1,Math.round(canvas.height*.6));
  gl.bindTexture(gl.TEXTURE_2D,r.texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,r.width,r.height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
  gl.bindFramebuffer(gl.FRAMEBUFFER,r.target);
  if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)return fallback();
  if(visible())draw();
 }
 function pass(p){gl.useProgram(p.program);gl.bindBuffer(gl.ARRAY_BUFFER,resources.buffer);gl.enableVertexAttribArray(p.position);gl.vertexAttribPointer(p.position,2,gl.FLOAT,false,0,0);gl.uniform1f(p.time,time)}
 function draw(){
  if(!resources||lost)return;
  const r=resources;gl.bindFramebuffer(gl.FRAMEBUFFER,r.target);gl.viewport(0,0,r.width,r.height);pass(r.fog);gl.uniform1f(r.fog.aspect,canvas.width/canvas.height);gl.drawArrays(gl.TRIANGLES,0,3);
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,canvas.width,canvas.height);pass(r.composite);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,r.texture);gl.uniform1i(r.composite.fog,0);gl.uniform2f(r.composite.size,canvas.width,canvas.height);gl.drawArrays(gl.TRIANGLES,0,3);
  canvas.dataset.frame=String(++frames);
 }
 function visible(){return document.body.classList.contains('landing')&&!document.hidden&&!document.querySelector('dialog[open]')}
 function animate(now){
  raf=0;if(!resources||lost||paused||!visible()){last=0;return}
  if(!last||now-last>=1000/30){time+=last?Math.min((now-last)/1000,.1):0;last=now;draw()}
  raf=requestAnimationFrame(animate);
 }
 function sync(){stop();backdrop.dataset.motion=!paused&&visible()?'running':'paused';if(resources&&!lost&&visible()){draw();if(!paused)raf=requestAnimationFrame(animate)}}
 button.onclick=()=>{chosen=true;paused=!paused;controls();sync()};
 reduced.addEventListener('change',()=>{if(!chosen){paused=reduced.matches;controls();sync()}});
 document.addEventListener('visibilitychange',sync);addEventListener('resize',resize);
 new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['class']});
 document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(sync).observe(dialog,{attributes:true,attributeFilter:['open']}));
 canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();lost=true;fallback('WebGL context lost')});
 canvas.addEventListener('webglcontextrestored',()=>{resources=null;lost=false;initialize()});
 initialize();
})();
