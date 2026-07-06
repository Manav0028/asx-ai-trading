import { useRealtimeChartAILive } from './hooks/useRealtimeChartAILive';
import { Header } from './components/Header';
import { Chart } from './components/Chart';
import { Rail } from './components/Rail';

const BEGINNER_MODE_DEFAULT = true;

function LiveApp() {
  const rc = useRealtimeChartAILive(BEGINNER_MODE_DEFAULT);

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
        ticker={rc.ticker}
        availableTickers={rc.availableTickers}
        onSelectTicker={rc.switchTicker}
        activeSource={rc.activeSource}
      />

      <main id="rcai-main" style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Chart canvasRef={rc.canvasRef} chartStatus={rc.chartStatus} ticker={rc.ticker} direction={rc.direction} />
        <Rail
          phase={rc.phase}
          dispScore={rc.dispScore}
          bd={rc.bd}
          autoTrade={rc.autoTrade}
          pnl={rc.pnl}
          patternName={rc.patternName}
          direction={rc.direction}
          entry={rc.entry}
          stop={rc.stop}
          target={rc.target}
          rr={rc.rr}
          posMeta={rc.posMeta}
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

export default LiveApp;
