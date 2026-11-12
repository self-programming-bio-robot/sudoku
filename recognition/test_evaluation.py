import unittest

import numpy as np

from data import LABELS, combine_samples
from evaluation import ERASE, REJECT, calibrate_erase_threshold, candidate_actions, legacy_actions


class RecognitionTest(unittest.TestCase):
    def test_maximum_score_and_strict_thresholds_choose_actions(self):
        scores = np.zeros((6, len(LABELS)), dtype=np.float32)
        scores[0, 4] = 0.9
        scores[1, ERASE] = 0.9
        scores[2, 3] = 0.5
        scores[3, ERASE] = 0.75
        scores[4, [4, ERASE]] = [0.7, 0.72]
        scores[5, [0, ERASE]] = [0.92, 0.9]
        np.testing.assert_array_equal(candidate_actions(scores, 0.75), [4, ERASE, REJECT, REJECT, REJECT, 0])
        self.assertEqual(candidate_actions(scores[1:2], None)[0], REJECT)

    def test_calibration_rejects_the_highest_false_erase(self):
        scores = np.zeros((4, len(LABELS)), dtype=np.float32)
        scores[:, ERASE] = [0.75, 0.5, 0.9, 0.75]
        labels = np.array([2, REJECT, ERASE, ERASE])
        threshold = calibrate_erase_threshold(scores, labels)
        self.assertEqual(threshold, 0.75)
        np.testing.assert_array_equal(candidate_actions(scores, threshold), [REJECT, REJECT, ERASE, REJECT])
        self.assertIsNone(calibrate_erase_threshold(scores[[0, 3]], labels[[0, 3]]))

    def test_legacy_zero_and_low_confidence_both_erase(self):
        scores = np.zeros((3, len(LABELS)), dtype=np.float32)
        scores[0, 0] = 0.9
        scores[1, 5] = 0.5
        scores[2, 5] = 0.75
        np.testing.assert_array_equal(legacy_actions(scores), [ERASE, ERASE, 4])

    def test_synthetic_labels_include_two_erase_kinds_and_all_zero_rejections(self):
        images = np.zeros((2, 28, 28), dtype=np.uint8)
        samples = combine_samples(images, np.array([1, 9]), 3, 2, seed=123)
        again = combine_samples(images, np.array([1, 9]), 3, 2, seed=123)
        np.testing.assert_array_equal(samples.images, again.images)
        np.testing.assert_array_equal(samples.labels[:2], [0, 8])
        targets = samples.targets()
        self.assertEqual(int(targets[:, ERASE].sum()), 6)
        self.assertEqual(int((targets.sum(axis=1) == 0).sum()), 6)
        self.assertEqual(set(samples.kinds[samples.labels == ERASE]), {"cross", "scribble"})


if __name__ == "__main__":
    unittest.main()
