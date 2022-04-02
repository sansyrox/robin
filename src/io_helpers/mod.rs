use std::collections::HashMap;

use std::fs::File;
use std::io::Read;

use actix_web::HttpResponseBuilder;

// this should be something else
// probably inside the submodule of the http router
#[inline]
pub fn apply_headers(response: &mut HttpResponseBuilder, headers: HashMap<String, String>) {
    for (key, val) in (headers).iter() {
        response.insert_header((key.clone(), val.clone()));
    }
}

/// A function to read lossy files and serve it as a html response
///
/// # Arguments
///
/// * `file_path` - The file path that we want the function to read
///
// ideally this should be async
pub fn read_file(file_path: &str) -> String {
    let mut file = File::open(file_path).unwrap();
    let mut buf = vec![];
    file.read_to_end(&mut buf).unwrap();
    String::from_utf8_lossy(&buf).to_string()
}
