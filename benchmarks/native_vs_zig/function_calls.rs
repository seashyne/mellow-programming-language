#[inline(never)]
fn add(a: i64, b: i64) -> i64 {
    a + b
}

fn main() {
    let n: i64 = 200_000;
    let mut i: i64 = 0;
    let mut total: i64 = 0;

    while i < n {
        total = add(total, i);
        i += 1;
    }

    println!("{}", total);
}
