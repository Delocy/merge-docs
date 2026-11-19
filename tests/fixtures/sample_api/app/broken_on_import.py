raise RuntimeError("this module must never be imported by merge-docs")

from fastapi import APIRouter

router = APIRouter(prefix="/boom")


@router.get("/x")
def x():
    ...
