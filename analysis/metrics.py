# Copyright 2022 OpenMined.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Dataclasses with Utility Analysis result metrics."""
from enum import Enum

import pipeline_dp
from dataclasses import dataclass
from typing import List, Optional
import math


@dataclass
class SumMetrics:
    """Stores per-partition metrics for SUM utility analysis.

    It is also used to store COUNT and PRIVACY_ID_COUNT per-partition metrics.

    Attributes:
        sum: actual sum of contributions per partition.
        per_partition_error_min: the amount of error due to contribution min clipping.
        per_partition_error_max: the amount of error due to contribution max clipping.
        expected_cross_partition_error: the expected amount of error due to cross-partition contribution bounding.
        std_cross_partition_error: the standard deviation of the error due to cross-partition contribution bounding.
        std_noise: the noise standard deviation.
        noise_kind: the type of noise used.

    s.t. the following holds (where E stands for Expectation):
    E(sum_after_contribution_bounding) = sum + E(error)
    where E(error) = per_partition_error_min + per_partition_error_max + expected_cross_partition_error
    """
    sum: float
    per_partition_error_min: float
    per_partition_error_max: float
    expected_cross_partition_error: float
    std_cross_partition_error: float
    std_noise: float
    noise_kind: pipeline_dp.NoiseKind


class AggregateMetricType(Enum):
    PRIVACY_ID_COUNT = 'privacy_id_count'
    COUNT = 'count'
    SUM = 'sum'


# TODO(dvadym): Remove he following dataclasses, when the new ones are used.
@dataclass
class AggregateErrorMetrics:
    """Stores aggregate cross-partition metrics for utility analysis.

    All attributes in this dataclass are averages across partitions; except for
    ratio_* attributes, which are simply the ratios of total data dropped
    aggregated across partitions.
    """
    metric_type: AggregateMetricType

    ratio_data_dropped_l0: float
    ratio_data_dropped_linf: float
    # This cannot be computed at PartitionSelectionMetrics and needs to be
    # computed for each aggregation separately, since it takes into account data
    # drop from contribution bounding and that is aggregation-specific.
    ratio_data_dropped_partition_selection: float

    error_l0_expected: float
    error_linf_expected: float
    error_linf_min_expected: float
    error_linf_max_expected: float
    error_expected: float
    error_l0_variance: float
    error_variance: float
    error_quantiles: List[float]
    rel_error_l0_expected: float
    rel_error_linf_expected: float
    rel_error_linf_min_expected: float
    rel_error_linf_max_expected: float
    rel_error_expected: float
    rel_error_l0_variance: float
    rel_error_variance: float
    rel_error_quantiles: List[float]

    # The following error metrics include error from dropped partitions.
    #
    # Consider the following example with a single partition to see how they are
    # different from abs/rel_error_expected metrics:
    #
    # Given 1 partition with probability_to_keep=0.4, actual_count=100,
    # abs_error_expected=-50;
    # -> abs_error_expected = (0.4*-50)/0.4=-50
    # -> abs_error_expected_w_dropped_partitions = 0.4*-50+0.6*-100=-80
    #
    # When public partitions are used, these will be exactly equal to
    # abs/rel_error_expected.
    error_expected_w_dropped_partitions: float
    rel_error_expected_w_dropped_partitions: float

    noise_std: float

    # RMSE = sqrt(bias**2 + variance), more details in
    # https://en.wikipedia.org/wiki/Bias-variance_tradeoff.
    def absolute_rmse(self) -> float:
        return math.sqrt(self.error_expected**2 + self.error_variance)

    def relative_rmse(self) -> float:
        return math.sqrt(self.rel_error_expected**2 + self.rel_error_variance)


@dataclass
class PartitionSelectionMetrics:
    """Stores aggregate metrics about partition selection."""

    num_partitions: float
    dropped_partitions_expected: float
    dropped_partitions_variance: float


@dataclass
class AggregateMetrics:
    """Stores result of the utility analysis for specific input parameters.

    Attributes:
        input_aggregate_params: input parameters for which this utility analysis
          was computed.

        count_metrics: utility analysis of count. It is non None, if Count
          metric is in input_aggregate_params.metrics.
        privacy_id_count_metrics: utility analysis of sum. It is non None, if
          Sum  metric is in input_aggregate_params.metrics.
        partition_selection_metrics: utility analysis of selected partition. It
          is not None if the utility analysis is for private partition selection.
    """
    input_aggregate_params: pipeline_dp.AggregateParams

    count_metrics: Optional[AggregateErrorMetrics] = None
    privacy_id_count_metrics: Optional[AggregateErrorMetrics] = None
    partition_selection_metrics: Optional[PartitionSelectionMetrics] = None


# New dataclasses. They will be used as the output of Utility analysis in the
# next PRs.


@dataclass
class MeanVariance:
    mean: float
    var: float


@dataclass
class ContributionBoundingErrors:
    """Contains an error breakdown by types of contribution bounding.

    Attributes:
        l0: max_partition_contributed (aka l0) bounding error. The output of l0
          bounding is a random variable for each partition. Its distribution is
          close to normal when number of contribution per partition is large.
        linf: per partition (aka linf) bounding error. The output of linf
          bounding is deterministic for each partition.
        linf_min & linf_max: represents error due to min & max contribution
          bounding, respectively (only populated for Sum metrics). It is
          deterministic for each partition.
    """
    l0: MeanVariance
    linf: float
    linf_min: float
    linf_max: float


@dataclass
class ValueErrors:
    """Errors between actual and dp metric.

    This class describes breakdown of errors for (dp_value - actual_value),
    where value can be a metric like count, sum etc. The value error is a random
    variable and it comes from different sources - contribution bounding error
    and DP noise. This class contains different error metrics.

    All attributes correspond to the errors computed per partition and then
    averaged across partitions, e.g.
      rmse_per_partition = sqrt(E(dp_value - actual_value)^2)
      self.rmse = mean(rmse_per_partition)

    Attributes:
        bounding_errors: contribution bounding errors.
        bias: averaged across partitions E(dp_value - actual_value).
        variance: averaged across partitions Var(dp_value - actual_value).
        rmse: averaged across partitions sqrt(E(dp_value - actual_value)^2).
        l1: averaged across partitions E|dp_value - actual_value|.
        with_dropped_partitions: error which takes into consideration partitions
          dropped due to partition selection. See example below.
    """
    bounding_errors: ContributionBoundingErrors
    bias: float
    variance: float
    rmse: float
    l1: float

    # The following error metrics include error from dropped partitions.
    #
    # Consider the following example with a single partition to see how they are
    # different from abs/rel_error_expected metrics:
    #
    # Given 1 partition with probability_to_keep=0.4, actual_count=100,
    # abs_error_expected=-50;
    # -> abs_error_expected = (0.4*-50)/0.4=-50
    # -> abs_error_expected_w_dropped_partitions = 0.4*-50+0.6*-100=-80
    #
    # When public partitions are used, these will be exactly equal to
    # abs/rel_error_expected.
    with_dropped_partitions: float


@dataclass
class DataDropInfo:
    """Information about the data dropped during different DP stages.

    Attributes:
        l0: ratio of data dropped during of l0 contribution bounding.
        linf: ratio of data dropped during of linf contribution bounding.
        partition_selection: ratio of data dropped because of partition
          selection.

    """
    l0: float
    linf: float

    # This cannot be computed at PartitionSelectionUtility and needs to be
    # computed for each aggregation separately, since it takes into account data
    # drop from contribution bounding and that is aggregation-specific.
    partition_selection: float


@dataclass
class MetricUtility:
    """Stores aggregate cross-partition metrics for utility analysis.

    Attributes:
        metric: DP metric for which this analysis was performed.
        num_dataset_partitions: the number of partitions in dataset.
        num_non_public_partitions: the number of partitions dropped because
          of public partitions.
        num_empty_partitions: the number of empty partitions added because of
          public partitions.
        noise_std: the standard deviation of added noise.
        noise_kind: the noise kind (Laplace or Gaussian)
        ratio_data_dropped: the information about dropped data.
        absolute_error: error in terms of (dp_value - actual_value).
        relative_error: error in terms of (dp_value - actual_value)/actual_value.
    """
    metric: pipeline_dp.Metrics
    num_dataset_partitions: int
    num_non_public_partitions: int
    num_empty_partitions: int

    # Noise information.
    noise_std: float
    noise_kind: pipeline_dp.NoiseKind

    # Dropped data breakdown.
    ratio_data_dropped: DataDropInfo

    # Value errors
    absolute_error: ValueErrors
    relative_error: ValueErrors


@dataclass
class PrivatePartitionSelectionUtility:
    """Stores aggregate metrics about partition selection."""

    strategy: pipeline_dp.PartitionSelectionStrategy
    num_partitions: float
    dropped_partitions: MeanVariance
    ratio_dropped_data: float


@dataclass
class UtilityReport:
    """Stores result of the utility analysis for specific input parameters.

    Attributes:
        input_aggregate_params: input parameters for which this utility analysis
          was computed.
        metric_errors: utility analysis of metrics (e.g. COUNT, SUM,
          PRIVACY_ID_COUNT).
        partition_selection_metrics: utility analysis of selected partition.
    """
    input_aggregate_params: pipeline_dp.AggregateParams

    metric_errors: Optional[List[MetricUtility]] = None
    partition_selection_metrics: Optional[
        PrivatePartitionSelectionUtility] = None
