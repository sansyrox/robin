from typing import TypedDict

from robyn import Robyn, Request, jsonify, OpenAPI, SubRouter
from robyn.openapi import OpenAPIInfo, Contact, License, ExternalDocumentation, Components

app = Robyn(
    file_object=__file__,
    openapi=OpenAPI(
        info=OpenAPIInfo(
            title="Sample Pet Store App",
            description=" This is a sample server for a pet store.",
            termsOfService=" https://example.com/terms/",
            version=" 1.0.1",
            contact=Contact(
                name="API Support",
                url="https://www.example.com/support",
                email="support@example.com",
            ),
            license=License(
                name="Apache 2.0",
                url="https://www.apache.org/licenses/LICENSE-2.0.html",
            ),
            servers=[
                # Server(
                #     url="//",
                #     description="Debug environment"
                # ),
                # Server(
                #     url="https://example.com/api/v1/",
                #     description="Production environment"
                # ),
            ],
            externalDocs=ExternalDocumentation(description="Find more info here", url="https://example.com/"),
            components=Components(),
        ),
    ),
)


@app.get("/")
async def welcome():
    """hiiii"""
    return "hiiiiii"


class GetParams(TypedDict):
    appointment_id: str
    year: int


@app.get("/users/:name/:age", openapi_tags=["Users"])
async def get_user(r: Request, query_params=GetParams):
    """Get User by ID"""
    return {"message": f"User {r.path_params['name']} : {r.path_params['age']}"}


@app.delete("/users/:name/:age", openapi_tags=["Users"])
async def delete_user(r: Request):
    """Delete User by ID"""
    return jsonify(r.path_params)


doctor_router = SubRouter(__name__, prefix="/doctor")


@doctor_router.get("/")
async def doctor_welcome():
    """hiiii"""
    return "doctor_hiiiiii"


@doctor_router.get("/users/:name/:age")
async def doctor_get_user(r: Request):
    """Get User by ID"""
    return {"message": f"doctor_User {r.path_params['name']} : {r.path_params['age']}"}


@doctor_router.delete("/users/:name/:age")
async def doctor_delete_user(r: Request):
    """Delete User by ID"""
    return f"doctor_{jsonify(r.path_params)}"


app.include_router(doctor_router)

if __name__ == "__main__":
    app.start()

# query params ->> typed dict
# subrouter impl for openapi

# add_direcotry
