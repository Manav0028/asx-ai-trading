import { useRealtimeChartAI, ENTRY, STOP, TARGET, SHARES, NOTIONAL, RISK } from './hooks/useRealtimeChartAI';
import { Header } from './components/Header';
import { Chart } from './components/Chart';
import { Rail } from './components/Rail';

const BEGINNER_MODE_DEFAULT = true;
const AUTO_TRADE_DEFAULT = false;

function App() {
  const rc = useRealtimeChartAI(BEGINNER_MODE_DEFAULT, AUTO_TRADE_DEFAULT);

  return (
    <div
      id="rcai-root"
      style={{
        height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden',
        fontFamily: 'var(--font-sans)', fontSize: 14, background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}
    >
      <Header
        tf={rc.tf}
        setTf={rc.setTf}
        beginner={rc.beginner}
        toggleBeginner={rc.toggleBeginner}
        autoTrade={rc.autoTrade}
        toggleAutoTrade={rc.toggleAutoTrade}
      />

      <main id="rcai-main" style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Chart canvasRef={rc.canvasRef} chartStatus={rc.chartStatus} />
        <Rail
          phase={rc.phase}
          dispScore={rc.dispScore}
          bd={rc.bd}
          pnl={rc.pnl}
          patternName="Bullish order-block retest"
          direction="long"
          entry={ENTRY}
          stop={STOP}
          target={TARGET}
          rr={2.0}
          posMeta={`${SHARES} sh · $${NOTIONAL.toLocaleString()} · risk $${RISK}`}
          tab={rc.tab}
          setTab={rc.setTab}
          messages={rc.messages}
          typing={rc.typing}
          draft={rc.draft}
          setDraft={rc.setDraft}
          feedRef={rc.feedRef}
          ask={rc.ask}
          send={rc.send}
          journal={rc.journal}
          trades={rc.trades}
          expandedTrade={rc.expandedTrade}
          toggleTrade={rc.toggleTrade}
        />
      </main>
    </div>
  );
}

export default App;
