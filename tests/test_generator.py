import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.generator import generate
class T(unittest.TestCase):
    rows = [[str(20 + i % 30), "AB"[i % 2]] for i in range(400)]
    def test_shape(self):
        out, tvd, _ = generate(["age", "g"], self.rows, 1.0, 50)
        self.assertEqual(len(out), 50); self.assertTrue(0 <= tvd <= 1)
    def test_more_epsilon_less_loss(self):
        lo = sum(generate(["a", "g"], self.rows, 0.05, 400)[1] for _ in range(20))
        hi = sum(generate(["a", "g"], self.rows, 20, 400)[1] for _ in range(20))
        self.assertLess(hi, lo)
if __name__ == "__main__": unittest.main()
