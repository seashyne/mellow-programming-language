fn main() {
    let values: [i64; 5] = [1, 2, 3, 4, 5];
    let n: i64 = 500_000;
    let mut i: i64 = 0;
    let mut total: i64 = 0;

    while i < n {
        total += values[(i % 5) as usize];
        i += 1;
    }

    println!("{}", total);
}
