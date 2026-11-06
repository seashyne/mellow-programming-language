fn main() {
    let n: usize = 2000;
    let mut text: Vec<u8> = vec![0; n];
    let mut i: usize = 0;

    while i < n {
        text[i] = b'a';
        i += 1;
    }

    println!("{}", text.len());
}
