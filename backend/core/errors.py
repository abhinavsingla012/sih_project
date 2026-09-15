from fastapi import HTTPException
def fail(status: int, code: str, message: str, **details):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message, 'details': details})