"""Testes do motor da Auditoria (python -m unittest discover -s tests)."""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy import optimize, stats

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import auditoria_motor as M  # noqa: E402

SJ_T1 = [4450, 8932, 209, 353, 290, 20, 25, 249, 381, 3765, 18674]  # município de teste (contagens reais do 1º turno)
SJ_T2 = [5434, 8933, 177, 261, 3872, 18677]


class Reconciliacao(unittest.TestCase):
    def test_silva_jardim(self):
        r = M.reconciliar(SJ_T1, SJ_T2)
        self.assertTrue(all(r["identidades"].values()))
        self.assertEqual(r["variacao"]["Lula"], 984)
        self.assertEqual(r["variacao"]["Flávio"], 1)
        self.assertEqual(r["variacao"]["comparecimento"], -104)
        self.assertEqual(r["ganho_finalistas"], 985)
        self.assertEqual(r["variacao_demais_categorias"], -1089)  # 897 eliminados + 72 brancos + 120 nulos
        self.assertEqual(r["variacao"]["Abstenção"], 107)

    def test_identidade_quebrada(self):
        t2 = list(SJ_T2)
        t2[0] += 5  # 5 votos a mais sem mudar o comparecimento
        self.assertFalse(M.reconciliar(SJ_T1, t2)["identidades"]["comparecimento_2_confere"])


class Limites(unittest.TestCase):
    def lp_min_cruzada(self, t1, t2):
        """Migração mínima entre finalistas por programação linear (3 origens × 3 destinos)."""
        c1, c2, ap1, ap2 = M.categorias(t1, t2)
        novos = max(0, ap2 - ap1)
        sup = [c1["Lula"], c1["Flávio"], c1["Demais"] + c1["Branco"] + c1["Nulo"] + c1["Abstenção"] + novos]
        dem = [c2["Lula"], c2["Flávio"], c2["Branco"] + c2["Nulo"] + c2["Abstenção"]]
        dem[2] += sum(sup) - sum(dem)  # fecha os totais (aptos que saíram do cadastro)
        cst = np.zeros(9)
        cst[1] = cst[3] = 1  # L→F e F→L
        A, b = [], []
        for i in range(3):
            row = np.zeros(9); row[i * 3:i * 3 + 3] = 1; A.append(row); b.append(sup[i])
        for j in range(3):
            row = np.zeros(9); row[j::3] = 1; A.append(row); b.append(dem[j])
        res = optimize.linprog(cst, A_eq=np.array(A), b_eq=np.array(b), bounds=[(0, None)] * 9, method="highs")
        return res.fun

    def test_fechada_igual_lp(self):
        rng = np.random.default_rng(1)
        for _ in range(300):
            t1 = list(rng.integers(0, 400, 10)) + [0]
            t1[10] = sum(t1[:10])
            L2, F2, B2, N2 = rng.integers(0, 900, 4)
            A2 = max(0, t1[10] - (L2 + F2 + B2 + N2))
            ap2 = L2 + F2 + B2 + N2 + A2
            t2 = [L2, F2, B2, N2, A2, ap2]
            lim = M.limites(t1, t2)
            esperado = lim["migracao_minima_flavio_para_lula"] + lim["migracao_minima_lula_para_flavio"]
            self.assertAlmostEqual(esperado, self.lp_min_cruzada(t1, t2), delta=1e-6)

    def test_silva_jardim_sem_migracao(self):
        lim = M.limites(SJ_T1, SJ_T2)
        self.assertTrue(lim["possivel_sem_migracao_entre_finalistas"])
        self.assertEqual(lim["disponivel_sem_finalistas"], 897 + 249 + 381 + 3765 + 3)
        self.assertLess(lim["captacao_necessaria_lula"], 0.2)

    def test_saldo_liquido_silva_jardim(self):
        lim = M.limites(SJ_T1, SJ_T2)
        self.assertEqual(lim["brancos_nulos_liberados"], 72 + 120)
        self.assertEqual(lim["abstencao_liberada"], 0)  # a abstenção subiu (+107)
        self.assertAlmostEqual(lim["lula_minimo_dos_eliminados"], (984 - 192) / 897)  # 88,3%
        self.assertAlmostEqual(lim["flavio_ganho_sobre_eliminados"], 1 / 897)

    def test_frechet(self):
        f = M.frechet([10, 5], [8, 7])
        self.assertEqual(f[0][0], [3, 8])
        self.assertEqual(f[1][1], [0, 5])


class MonteCarlo(unittest.TestCase):
    def setUp(self):
        self.c = M.origens_6(SJ_T1)
        self.P = M.matriz_6([[97, 0, 0, 0, 3], [3, 94, 0, 1, 2]] + [[40, 50, 2, 5, 3]] * 5 + [[60, 5, 25, 5, 5], [55, 5, 2, 35, 3], [10, 3, 1, 1, 85]], SJ_T1)

    def test_reprodutivel(self):
        a, _ = M.simular(self.c, self.P, 300.0, 5000, np.random.default_rng(42))
        b, _ = M.simular(self.c, self.P, 300.0, 5000, np.random.default_rng(42))
        self.assertTrue(np.array_equal(a, b))

    def test_momentos_batem_com_simulacao(self):
        for alpha in (None, 50.0, 2000.0):
            sim, _ = M.simular(self.c, self.P, alpha, 60_000, np.random.default_rng(3))
            m, sd = M.momentos(self.c, self.P, alpha)
            self.assertAlmostEqual(float(sim.mean()), m, delta=4 * sd / math.sqrt(60_000) + 1e-4)
            self.assertAlmostEqual(float(sim.std()) / sd, 1.0, delta=0.06)

    def test_calibracao_recupera_alpha_e_p_uniforme(self):
        rng = np.random.default_rng(7)
        alpha = 400.0
        unid = []
        for _ in range(400):
            c = (self.c * rng.uniform(0.3, 3)).round()
            s, _ = M.simular(c, self.P, alpha, 1, rng)
            unid.append((c, self.P, float(s[0])))
        a = M.calibrar_alpha(unid)
        self.assertTrue(alpha / 2 < a < alpha * 2, a)
        z = [(s - m) / sd for c, P, s in unid for m, sd in [M.momentos(c, P, a)]]
        p = 2 * stats.norm.sf(np.abs(z))
        self.assertGreater(stats.kstest(p, "uniform").pvalue, 0.001)

    def test_evento_raro_nao_e_zero(self):
        sim = np.random.default_rng(0).normal(0.5, 0.01, 10_000)
        r = M.prob_extrema(sim, 0.60)  # 10 desvios-padrão
        self.assertEqual(r["extremos"], 0)
        self.assertEqual(r["metodo"], "extrapolacao_normal")
        self.assertGreater(r["p"], 0)
        self.assertAlmostEqual(r["p_hi"], 1 - 0.025 ** (1 / 10_000), delta=1e-5)

    def test_valor_exato_menor_que_extremo(self):
        sim, LL = M.simular(self.c, self.P, 300.0, 20_000, np.random.default_rng(5))
        p_ext = M.prob_extrema(sim, float(np.median(sim)))["p"]
        self.assertLess(M.prob_valor_exato(LL, int(np.median(LL))), p_ext)


class Apresentacao(unittest.TestCase):
    def test_um_em_n(self):
        self.assertEqual(M.um_em_n(1 / 500), "1 em 500")
        self.assertEqual(M.um_em_n(1 / 25_000), "1 em 25 mil")
        self.assertEqual(M.um_em_n(1 / 1.5e6), "1 em 1,5 milhão")
        self.assertEqual(M.um_em_n(1 / 5e7), "1 em 50 milhões")
        self.assertEqual(M.um_em_n(1 / 2e9), "1 em 2 bilhões")
        self.assertIsNone(M.um_em_n(0))

    def test_mega(self):
        m = M.mega(1 / 500e6)
        self.assertAlmostEqual(m["razao"], 500e6 / 50_063_860, places=6)  # ~10 vezes menos provável
        self.assertAlmostEqual(m["n"], math.log(1 / 500e6) / math.log(1 / 50_063_860), places=9)

    def test_fdr(self):
        p = np.random.default_rng(2).uniform(size=200) ** 3
        self.assertTrue(np.allclose(M.bh_fdr(p), stats.false_discovery_control(p)))


class Transferencia(unittest.TestCase):
    """scripts/23_transferencia.py: caudas exatas em log10."""
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("t23", RAIZ / "scripts" / "23_transferencia.py")
        cls.T = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.T)

    def test_cauda_binomial_moderada(self):
        v = self.T.cauda_binom(np.array([60.0]), np.array([100.0]), np.array([0.5]))[0]
        self.assertAlmostEqual(v, math.log10(stats.binom.sf(59, 100, 0.5)), places=6)

    def test_cauda_binomial_extrema_silva_jardim(self):
        v = self.T.cauda_binom(np.array([792.0]), np.array([897.0]), np.array([0.25193]))[0]
        self.assertTrue(-360 < v < -330, v)  # ~10^-348: “45 Mega-Senas” sob eleitores independentes

    def test_betabinomial_mais_largo(self):
        b = self.T.cauda_binom(np.array([600.0]), np.array([897.0]), np.array([0.46]))[0]
        bb = self.T.cauda_betabinom(np.array([600.0]), np.array([897.0]), np.array([0.46]), 0.3)[0]
        self.assertGreater(bb, b)

    def test_impossivel_sem_migracao(self):
        self.assertEqual(self.T.cauda_binom(np.array([10.0]), np.array([5.0]), np.array([0.5]))[0], -np.inf)


class SaidaPublicada(unittest.TestCase):
    """Checa o contrato JSON gerado por 22_auditoria.py, se já existir."""
    ARQ = RAIZ / "portal" / "dados" / "auditoria" / "nacional.json"

    @unittest.skipUnless(ARQ.exists(), "rode scripts/22_auditoria.py antes")
    def test_contrato(self):
        N = json.loads(self.ARQ.read_text())
        self.assertEqual(N["schema_version"], "1.0")
        for k in ("fonte", "seed", "simulacoes", "processado_em", "evento"):
            self.assertIn(k, N["metadados"])
        self.assertEqual(N["contagens"]["secoes"], N["qualidade"]["secoes"])
        self.assertEqual(len(N["ufs"]), 28)
        C = N["ranking_municipios"]["colunas"]
        for linha in N["ranking_municipios"]["linhas"]:
            p = linha[C.index("p")]
            self.assertTrue(p is None or 0 < p <= 1)

    @unittest.skipUnless(ARQ.exists(), "rode scripts/22_auditoria.py antes")
    def test_reconciliacao_e_passe_profundo_publicados(self):
        profundos = 0
        for arq in (RAIZ / "portal" / "dados" / "auditoria" / "uf").glob("*.json"):
            U = json.loads(arq.read_text())
            for m in U["municipios"]:
                t1, t2 = m["contagens"]["turno1"], m["contagens"]["turno2"]
                self.assertEqual(m["reconciliacao"]["variacao"]["Lula"], t2[0] - t1[0])
                profundos += bool(m["monte_carlo"]["profundo"])
        self.assertEqual(profundos, 20)  # os 20 municípios mais distantes do esperado


if __name__ == "__main__":
    unittest.main()
