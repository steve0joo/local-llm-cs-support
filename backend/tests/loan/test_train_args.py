"""train.py 인자: 체크포인트 보관 수는 v3와 같은 기본값(2)을 유지하고, 필요할 때만 늘린다(학습 설정 자체는 그대로)."""
from training.loan import train


def test_save_total_limit_defaults_to_the_v3_value_and_can_keep_every_epoch():
    assert train._parse_args([]).save_total_limit == 2
    assert train._parse_args(["--save-total-limit", "3"]).save_total_limit == 3


def test_v3_hyperparameters_are_unchanged_by_default():
    args = train._parse_args([])
    assert (args.lr, args.epochs, args.lora_r, args.lora_alpha, args.lora_dropout, args.micro_batch_size, args.grad_accum, args.seed) == (
        2e-4, 3.0, 16, 32, 0.05, 1, 16, 42)
