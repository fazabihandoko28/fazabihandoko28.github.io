A={'EARLY':'AWAL','PREPARE':'SIAGA','READY':'EKSEKUSI','HOLD':'TAHAN','PREPARE_EXIT':'LEPAS','EXIT':'JUAL','AVOID':'LEWATI','NO_DATA':'DATA MINIM'}
R={'LOW':'RENDAH','MEDIUM':'SEDANG','HIGH':'TINGGI','EXTREME':'EKSTREM','UNKNOWN':'BELUM ADA'}
L={'trend':'TREN','momentum':'MOMEN','volume':'VOLUME','liquidity':'LIKUID','risk':'RISIKO','breakout':'TEMBUS','relative_strength':'KUAT REL','market':'PASAR'}
class ExplainEngine:
    def compact_id(self,d):
        return {'SIMBOL':d.symbol,'AKSI':A[d.action.value],'EVIDENCE':round(d.score),'RISIKO':R[d.risk.value],'LOLOS':[L.get(x,x.upper()) for x in d.passed],'WASPADA':[L.get(x,x.upper()) for x in d.warnings],'VETO':[L.get(x,x.upper()) for x in d.vetoes],'PEMICU':d.next_trigger}
