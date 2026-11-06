fn main() {
    let n: i64 = 500_000;
    let mut i: i64 = 0;
    let mut total: i64 = 0;

    while i < n {
        if i % 2 == 0 {
            total += 3;
        } else {
            total += 1;
        }
        i += 1;
    }

    println!("{}", total);
}
