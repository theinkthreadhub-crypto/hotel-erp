import {createServer} from 'node:http';
import {timingSafeEqual} from 'node:crypto';
import {join,resolve} from 'node:path';
import makeWASocket,{useMultiFileAuthState,DisconnectReason} from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';
import {ReceiptOutbox} from './core.mjs';

const dir=resolve(process.env.BAILEYS_DATA_DIR||'./state');
const secret=process.env.BAILEYS_GATEWAY_SECRET||'';
const password=process.env.BAILEYS_ADMIN_PASSWORD||'';
if(secret.length<32||password.length<24)throw Error('Configure gateway and admin secrets');
const equals=(a,b)=>{const x=Buffer.from(a||''),y=Buffer.from(b||'');return x.length===y.length&&x.length>0&&timingSafeEqual(x,y);};
let sock=null,connected=false,qr='',reconnect=null;
const outbox=new ReceiptOutbox(dir,async(to,text)=>{
  if(!connected||!sock)throw Error('Disconnected');
  const result=await sock.sendMessage(to+'@s.whatsapp.net',{text});
  if(!result?.key?.id)throw Error('Not acknowledged');
  return result.key.id;
},()=>connected&&!!sock);
await outbox.init();
async function connect(){
  const {state,saveCreds}=await useMultiFileAuthState(join(dir,'auth'));
  const next=makeWASocket({auth:state,logger:pino({level:'silent'}),markOnlineOnConnect:false,syncFullHistory:false,printQRInTerminal:false});
  sock=next;connected=false;
  next.ev.on('creds.update',saveCreds);
  next.ev.on('connection.update',u=>{
    if(sock!==next)return;
    if(u.qr){qr=u.qr;connected=false;}
    if(u.connection==='open'){qr='';connected=true;}
    if(u.connection==='close'){
      qr='';connected=false;sock=null;
      if(u.lastDisconnect?.error?.output?.statusCode===DisconnectReason.loggedOut)return;
      if(!reconnect)reconnect=setTimeout(()=>{reconnect=null;reconnectSafe();},7000);
    }
  });
  // No inbound handlers, no auto-replies, no contact discovery or bulk messaging.
}
const json=(res,code,body)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
const authorized=r=>r.headers.authorization?.startsWith('Bearer ')&&equals(r.headers.authorization.slice(7),secret);
function isAdmin(req){
  try{
    const header=req.headers.authorization||'';
    if(!header.startsWith('Basic '))return false;
    const [name,...rest]=Buffer.from(header.slice(6),'base64').toString('utf8').split(':');
    return name==='admin'&&equals(rest.join(':'),password);
  }catch{return false;}
}
async function readJson(req){
  let body='',n=0;
  for await(const data of req){n+=data.length;if(n>5000)throw Error('Too large');body+=data.toString();}
  return JSON.parse(body);
}
createServer(async(req,res)=>{
  const path=new URL(req.url,'http://local').pathname;
  if(req.method==='GET'&&path==='/health')return json(res,200,{connected,qrReady:!!qr});
  if(path==='/admin'&&req.method==='GET'){
    if(!isAdmin(req)){res.writeHead(401,{'WWW-Authenticate':'Basic realm="Setu WhatsApp"','Cache-Control':'no-store'});return res.end();}
    const img=qr?await QRCode.toDataURL(qr,{width:320}):'';
    res.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store','X-Frame-Options':'DENY'});
    return res.end('<meta name="viewport" content="width=device-width,initial-scale=1"><title>Setu WhatsApp</title><main style="font:18px system-ui;text-align:center;margin:40px"><h2>Setu WhatsApp Receipt Sender</h2><p>'+
      (connected?'Connected':img?'Scan using WhatsApp Linked Devices':'Waiting for connection')+'</p>'+
      (img?'<img width="320" alt="Login QR" src="'+img+'">':'')+'<p><a href="/admin">Refresh</a></p></main>');
  }
  if(path==='/send'&&req.method==='POST'){
    if(!authorized(req))return json(res,401,{error:'Unauthorized'});
    try{
      const result=await outbox.submit(await readJson(req));
      return json(res,result.status==='not_connected'?503:200,result);
    }catch{return json(res,400,{error:'Invalid receipt request'});}
  }
  return json(res,404,{error:'Not found'});
}).listen(Number(process.env.PORT||3000),'0.0.0.0');
async function reconnectSafe(){
  try{await connect();}
  catch(e){
    connected=false;sock=null;qr='';
    console.error('WhatsApp session initialization failed; retrying without exposing credentials');
    if(!reconnect)reconnect=setTimeout(()=>{reconnect=null;reconnectSafe();},10000);
  }
}
reconnectSafe();
