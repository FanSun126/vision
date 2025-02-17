import io
from pathlib import Path

import pytest
import torch
from builtin_dataset_mocks import parametrize_dataset_mocks, DATASET_MOCKS
from torch.utils.data.datapipes.iter.grouping import ShardingFilterIterDataPipe as ShardingFilter
from torch.utils.data.graph import traverse
from torchdata.datapipes.iter import IterDataPipe, Shuffler
from torchvision.prototype import transforms, datasets
from torchvision.prototype.utils._internal import sequence_to_str


def test_coverage():
    untested_datasets = set(datasets.list()) - DATASET_MOCKS.keys()
    if untested_datasets:
        raise AssertionError(
            f"The dataset(s) {sequence_to_str(sorted(untested_datasets), separate_last='and ')} "
            f"are exposed through `torchvision.prototype.datasets.load()`, but are not tested. "
            f"Please add mock data to `test/builtin_dataset_mocks.py`."
        )


class TestCommon:
    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_smoke(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        if not isinstance(dataset, IterDataPipe):
            raise AssertionError(f"Loading the dataset should return an IterDataPipe, but got {type(dataset)} instead.")

    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_sample(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        try:
            sample = next(iter(dataset))
        except Exception as error:
            raise AssertionError("Drawing a sample raised the error above.") from error

        if not isinstance(sample, dict):
            raise AssertionError(f"Samples should be dictionaries, but got {type(sample)} instead.")

        if not sample:
            raise AssertionError("Sample dictionary is empty.")

    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_num_samples(self, dataset_mock, config):
        with dataset_mock.prepare(config) as mock_info:
            dataset = datasets.load(dataset_mock.name, **config)

        num_samples = 0
        for _ in dataset:
            num_samples += 1

        assert num_samples == mock_info["num_samples"]

    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_decoding(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        undecoded_features = {key for key, value in next(iter(dataset)).items() if isinstance(value, io.IOBase)}
        if undecoded_features:
            raise AssertionError(
                f"The values of key(s) "
                f"{sequence_to_str(sorted(undecoded_features), separate_last='and ')} were not decoded."
            )

    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_no_vanilla_tensors(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        vanilla_tensors = {key for key, value in next(iter(dataset)).items() if type(value) is torch.Tensor}
        if vanilla_tensors:
            raise AssertionError(
                f"The values of key(s) "
                f"{sequence_to_str(sorted(vanilla_tensors), separate_last='and ')} contained vanilla tensors."
            )

    @parametrize_dataset_mocks(DATASET_MOCKS)
    def test_transformable(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        next(iter(dataset.map(transforms.Identity())))

    @parametrize_dataset_mocks(
        DATASET_MOCKS,
        marks={
            "cub200": pytest.mark.xfail(
                reason="See https://github.com/pytorch/vision/pull/5187#issuecomment-1015479165"
            )
        },
    )
    def test_traversable(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        traverse(dataset)

    @parametrize_dataset_mocks(
        DATASET_MOCKS,
        marks={
            "cub200": pytest.mark.xfail(
                reason="See https://github.com/pytorch/vision/pull/5187#issuecomment-1015479165"
            )
        },
    )
    @pytest.mark.parametrize("annotation_dp_type", (Shuffler, ShardingFilter))
    def test_has_annotations(self, dataset_mock, config, annotation_dp_type):
        def scan(graph):
            for node, sub_graph in graph.items():
                yield node
                yield from scan(sub_graph)

        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        if not any(type(dp) is annotation_dp_type for dp in scan(traverse(dataset))):
            raise AssertionError(f"The dataset doesn't contain a {annotation_dp_type.__name__}() datapipe.")


@parametrize_dataset_mocks(DATASET_MOCKS["qmnist"])
class TestQMNIST:
    def test_extra_label(self, dataset_mock, config):
        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        sample = next(iter(dataset))
        for key, type in (
            ("nist_hsf_series", int),
            ("nist_writer_id", int),
            ("digit_index", int),
            ("nist_label", int),
            ("global_digit_index", int),
            ("duplicate", bool),
            ("unused", bool),
        ):
            assert key in sample and isinstance(sample[key], type)


@parametrize_dataset_mocks(DATASET_MOCKS["gtsrb"])
class TestGTSRB:
    def test_label_matches_path(self, dataset_mock, config):
        # We read the labels from the csv files instead. But for the trainset, the labels are also part of the path.
        # This test makes sure that they're both the same
        if config.split != "train":
            return

        with dataset_mock.prepare(config):
            dataset = datasets.load(dataset_mock.name, **config)

        for sample in dataset:
            label_from_path = int(Path(sample["image_path"]).parent.name)
            assert sample["label"] == label_from_path
