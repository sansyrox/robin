use pyo3::prelude::*;

use socket2::{Domain, Protocol, Socket, Type};
use std::net::SocketAddr;

#[pyclass]
#[derive(Debug)]
pub struct SocketHeld {
    pub socket: Socket,
}

#[pymethods]
impl SocketHeld {
    #[new]
    pub fn new(address: String, port: i32) -> PyResult<SocketHeld> {
        let socket = Socket::new(Domain::IPV4, Type::STREAM, Some(Protocol::TCP))?;
        println!("{}", address);
        let address: SocketAddr = address.parse()?;
        socket.set_reuse_address(true)?;
        //socket.set_reuse_port(true)?;
        socket.bind(&address.into())?;
        socket.listen(1024)?;

        Ok(SocketHeld { socket })
    }

    pub fn try_clone(&self) -> PyResult<SocketHeld> {
        let copied = self.socket.try_clone()?;
        Ok(SocketHeld { socket: copied })
    }
}

impl SocketHeld {
    pub fn get_socket(&self) -> Socket {
        self.socket.try_clone().unwrap()
    }
}
