from contextlib import asynccontextmanager
import hashlib,logging
from fastapi import FastAPI,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from core.config import TRUSTED_ORIGINS
from core.database import client,db,bus,indexes,uid
from modules.seed import seed
from modules.auth import router as auth_router
from modules.router import router as domain_router
from mock_departments.router import router as mock_router
from modules.events import ensure_group

@asynccontextmanager
async def lifespan(app):
    await indexes();await seed()
    try:await ensure_group()
    except Exception:logging.warning('Redis unavailable at startup; outbox remains durable')
    yield
    await bus.aclose();client.close()

app=FastAPI(title='Samanvay Interoperability Fabric',version='1.0.0',description='SIH26129 prototype. Identity and departments are simulated. Redis event transport and orchestration are real.',openapi_url='/api/openapi.json',docs_url='/api/docs',redoc_url=None,lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=list(TRUSTED_ORIGINS),allow_credentials=True,allow_methods=['GET','POST','PATCH','OPTIONS'],allow_headers=['Content-Type','X-CSRF-Token','Idempotency-Key','Authorization'])

@app.middleware('http')
async def request_controls(request:Request,call_next):
    request.state.request_id=uid('REQ')
    try:length=int(request.headers.get('content-length','0'))
    except ValueError:return JSONResponse(status_code=400,content={'error':{'code':'INVALID_LENGTH','message':'Invalid content length.'}})
    if length>65536:return JSONResponse(status_code=413,content={'error':{'code':'BODY_TOO_LARGE','message':'Request exceeds the 64 KB limit.'}})
    path=request.url.path
    if path.startswith('/api/') and request.method not in ('GET','OPTIONS') and not path.startswith(('/api/mock/','/api/internal/')):
        session=request.cookies.get('samanvay_session') or (request.client.host if request.client else 'anonymous')
        identity=hashlib.sha256(session.encode()).hexdigest()[:24]
        key=f'rate:{"login" if path=="/api/auth/login" else "mutate"}:{identity}'
        try:
            count=await bus.incr(key)
            if count==1:await bus.expire(key,60)
            if count>(30 if path=='/api/auth/login' else 120):return JSONResponse(status_code=429,headers={'Retry-After':'60'},content={'error':{'code':'RATE_LIMIT','message':'Too many requests. Please wait a minute.'}})
        except Exception:
            if path=='/api/auth/login':return JSONResponse(status_code=503,content={'error':{'code':'AUTH_UNAVAILABLE','message':'Sign-in protection is temporarily unavailable.'}})
    response=await call_next(request)
    response.headers['X-Request-ID']=request.state.request_id
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(HTTPException)
async def http_error(request,e):
    detail=e.detail if isinstance(e.detail,dict) else {'code':'REQUEST_FAILED','message':str(e.detail)}
    return JSONResponse(status_code=e.status_code,content={'error':{**detail,'requestId':getattr(request.state,'request_id',None),'retryable':e.status_code in (429,503)}})

@app.exception_handler(RequestValidationError)
async def validation_error(request,e):
    return JSONResponse(status_code=422,content={'error':{'code':'VALIDATION_ERROR','message':'Please check the required fields and permitted values.','requestId':getattr(request.state,'request_id',None),'details':[{'field':'.'.join(str(x) for x in err['loc']),'message':err['msg']} for err in e.errors()]}})

app.include_router(auth_router);app.include_router(domain_router);app.include_router(mock_router)
@app.get('/api/')
async def root():return {'service':'Samanvay','version':'1.0.0','prototype':True}