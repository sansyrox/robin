from abc import ABC, abstractmethod
from typing import Any, Coroutine, Optional, Union

from robyn.robyn import Headers, Identity, Request, Response
from robyn.status_codes import HTTP_401_UNAUTHORIZED


class AuthenticationNotConfiguredError(Exception):
    """
    This exception is raised when the authentication is not configured.
    """

    def __str__(self):
        return "Authentication is not configured. Use app.configure_authentication() to configure it."


class TokenGetter(ABC):
    @property
    def scheme(self) -> str:
        """
        Gets the scheme of the token.
        :return: The scheme of the token.
        """
        return self.__class__.__name__

    @classmethod
    @abstractmethod
    def get_token(cls, request: Request) -> Optional[str]:
        """
        Gets the token from the request.
        This method should not decode the token. Decoding is the role of the authentication handler.
        :param request: The request object.
        :return: The encoded token.
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def set_token(cls, request: Request, token: str):
        """
        Sets the token in the request.
        This method should not encode the token. Encoding is the role of the authentication handler.
        :param request: The request object.
        :param token: The encoded token.
        """
        raise NotImplementedError()


class AuthenticationHandler(ABC):
    def __init__(self, token_getter: TokenGetter):
        """
        Creates a new instance of the AuthenticationHandler class.
        This class is an abstract class used to authenticate a user.
        :param token_getter: The token getter used to get the token from the request.
        """
        self.token_getter = token_getter

    @property
    def unauthorized_response(self) -> Response:
        return Response(
            headers=Headers({"WWW-Authenticate": self.token_getter.scheme}),
            description="Unauthorized",
            status_code=HTTP_401_UNAUTHORIZED,
        )

    @abstractmethod
    def authenticate(self, request: Request) -> Union[Optional[Identity], Coroutine[Any, Any, Optional[Identity]]]:
        """
        Authenticates the user.
        :param request: The request object.
        :return: The identity of the user.
        """
        raise NotImplementedError()


class BearerGetter(TokenGetter):
    """
    This class is used to get the token from the Authorization header.
    The scheme of the header must be Bearer.
    """

    @classmethod
    def get_token(cls, request: Request) -> Optional[str]:
        if request.headers.contains("authorization"):
            authorization_header = request.headers.get("authorization")
        else:
            authorization_header = None

        if not authorization_header or not authorization_header.startswith("Bearer "):
            return None

        return authorization_header[7:]  # Remove the "Bearer " prefix

    @classmethod
    def set_token(cls, request: Request, token: str):
        request.headers["Authorization"] = f"Bearer {token}"
