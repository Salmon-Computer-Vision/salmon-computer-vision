import math
from statistics import *
from scipy import stats


class FishCountPerformance:
    """
    Use the formula here to calculate metrics
    https://www.medcalc.org/calc/comparison_of_means.php
    """

    def __init__(self, predictions: [int], ground_truths: [int]):
        super().__init__()
        self.predictions = predictions
        self.ground_truths = ground_truths

    def significance_level(self):
        """
        When the P-value (significance level) is less than 0.05 (P<0.05), the conclusion is
        that the two means are significantly different.
        """
        return stats.ttest_ind(self.predictions, self.ground_truths)

    def t_statisc(self):
        mean1 = mean(self.predictions)
        mean2 = mean(self.ground_truths)
        return (mean1 - mean2) / self.standard_error_of_means()

    def standard_error_of_means(self):
        """
        The standard error se of the difference between the two means
        """
        n1 = len(self.predictions)
        n2 = len(self.ground_truths)
        return self.pooled_standard_deviation() * math.sqrt((1 / n1) + (1 / n2))

    def pooled_standard_deviation(self):
        n1 = len(self.predictions)
        n2 = len(self.ground_truths)
        s1 = stdev(self.predictions)
        s2 = stdev(self.ground_truths)
        return math.sqrt(((n1 - 1) * pow(s1, 2) + (n2 - 1) * pow(s2, 2)) / (n1 + n2 - 2))
