fn main() {
    let n: i64 = 2_000_000;
    let mut i: i64 = 0;
    let mut total: i64 = 0;

    while i < n {
        total += i;
        i += 1;
    }

    println!("{}", total);
}
