use crate::types::PyFunction;

use actix::prelude::*;
use actix::{Actor, AsyncContext, StreamHandler};
use actix_web::{web, Error, HttpRequest, HttpResponse};
use actix_web_actors::ws;
use actix_web_actors::ws::WebsocketContext;
use pyo3::prelude::*;
use uuid::Uuid;

use std::collections::HashMap;
use std::sync::Arc;

/// Define HTTP actor
#[derive(Clone)]
struct MyWs {
    id: Uuid,
    router: HashMap<String, (PyFunction, u8)>,
    // can probably try removing arc from here
    // and use clone_ref()
    event_loop: Arc<PyObject>,
}

fn execute_ws_function(
    handler_function: &PyFunction,
    number_of_params: u8,
    event_loop: Arc<PyObject>,
    ctx: &mut ws::WebsocketContext<MyWs>,
    ws: &MyWs,
    // add number of params here
) {
    match handler_function {
        PyFunction::SyncFunction(handler) => Python::with_gil(|py| {
            let handler = handler.as_ref(py);
            // call execute function
            let op: PyResult<&PyAny> = match number_of_params {
                0 => handler.call0(),
                1 => handler.call1((ws.id.to_string(),)),
                // this is done to accomodate any future params
                2_u8..=u8::MAX => handler.call1((ws.id.to_string(),)),
            };

            let op: &str = op.unwrap().extract().unwrap();
            ctx.text(op);
        }),
        PyFunction::CoRoutine(handler) => {
            let fut = Python::with_gil(|py| {
                let handler = handler.as_ref(py);
                let coro = match number_of_params {
                    0 => handler.call0().unwrap(),
                    1 => handler.call1((ws.id.to_string(),)).unwrap(),
                    // this is done to accomodate any future params
                    2_u8..=u8::MAX => handler.call1((ws.id.to_string(),)).unwrap(),
                };
                pyo3_asyncio::into_future_with_loop((*(event_loop.clone())).as_ref(py), coro)
                    .unwrap()
            });
            let f = async move {
                let output = fut.await.unwrap();
                Python::with_gil(|py| {
                    let output: &str = output.extract(py).unwrap();
                    output.to_string()
                })
            };
            let f = f.into_actor(ws).map(|res, _, ctx| {
                ctx.text(res);
            });
            ctx.spawn(f);
        }
    }
}

// By default mailbox capacity is 16 messages.
impl Actor for MyWs {
    type Context = ws::WebsocketContext<Self>;

    fn started(&mut self, ctx: &mut WebsocketContext<Self>) {
        let handler_function = &self.router.get("connect").unwrap().0;
        let number_of_params = &self.router.get("connect").unwrap().1;
        execute_ws_function(
            handler_function,
            *number_of_params,
            self.event_loop.clone(),
            ctx,
            self,
        );

        println!("Actor is alive");
    }

    fn stopped(&mut self, ctx: &mut WebsocketContext<Self>) {
        let handler_function = &self.router.get("close").expect("No close function").0;
        let number_of_params = &self.router.get("close").unwrap().1;
        execute_ws_function(
            handler_function,
            *number_of_params,
            self.event_loop.clone(),
            ctx,
            self,
        );

        println!("Actor is dead");
    }
}

#[derive(Message)]
#[rtype(result = "Result<(), ()>")]
struct CommandRunner(String);

/// Handler for ws::Message message
impl StreamHandler<Result<ws::Message, ws::ProtocolError>> for MyWs {
    fn handle(&mut self, msg: Result<ws::Message, ws::ProtocolError>, ctx: &mut Self::Context) {
        match msg {
            Ok(ws::Message::Ping(msg)) => {
                println!("Ping message {:?}", msg);
                let handler_function = &self.router.get("connect").unwrap().0;
                let number_of_params = &self.router.get("connect").unwrap().1;
                println!("{:?}", handler_function);
                execute_ws_function(
                    handler_function,
                    *number_of_params,
                    self.event_loop.clone(),
                    ctx,
                    self,
                );
                ctx.pong(&msg)
            }

            Ok(ws::Message::Pong(msg)) => {
                println!("Pong message {:?}", msg);
                ctx.pong(&msg)
            }

            Ok(ws::Message::Text(_text)) => {
                // need to also passs this text as a param
                let handler_function = &self.router.get("message").unwrap().0;
                let number_of_params = &self.router.get("message").unwrap().1;
                execute_ws_function(
                    handler_function,
                    *number_of_params,
                    self.event_loop.clone(),
                    ctx,
                    self,
                );
            }

            Ok(ws::Message::Binary(bin)) => ctx.binary(bin),
            Ok(ws::Message::Close(_close_reason)) => {
                println!("Socket was closed");
                let handler_function = &self.router.get("close").expect("No close function").0;
                let number_of_params = &self.router.get("close").unwrap().1;
                execute_ws_function(
                    handler_function,
                    *number_of_params,
                    self.event_loop.clone(),
                    ctx,
                    self,
                );
            }
            _ => (),
        }
    }
}

pub async fn start_web_socket(
    req: HttpRequest,
    stream: web::Payload,
    router: HashMap<String, (PyFunction, u8)>,
    event_loop: Arc<PyObject>,
) -> Result<HttpResponse, Error> {
    // execute the async function here

    ws::start(
        MyWs {
            router,
            event_loop,
            id: Uuid::new_v4(),
        },
        &req,
        stream,
    )
}
