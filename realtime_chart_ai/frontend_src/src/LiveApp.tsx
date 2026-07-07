import { useRealtimeChartAILive } from './hooks/useRealtimeChartAILive';
import { Header } from './components/Header';
import { LiveChart } from './components/LiveChart';
import { Rail } from './components/Rail';
import { TradesTab } from './components/TradesTab';

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
        sectors={rc.sectors}
        heldTickers={rc.heldTickers}
      />

      <main id="rcai-main" style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <LiveChart
          candles={rc.candles}
          chartStatus={rc.chartStatus}
          ticker={rc.ticker}
          direction={rc.direction}
          entry={rc.entry}
          stop={rc.stop}
          target={rc.target}
          zones={rc.zones}
          prevClose={rc.prevClose}
          markers={rc.markers}
        />
        <Rail
          phase={rc.phase}
          dispScore={rc.dispScore}
          bd={rc.bd}
          pnl={rc.pnl}
          patternName={rc.patternName}
          direction={rc.direction}
          entry={rc.entry}
          stop={rc.stop}
          target={rc.target}
          rr={rc.rr}
          posMeta={rc.posMeta}
          hasOpenPosition={rc.hasOpenPosition}
          ticker={rc.ticker}
          price={rc.price}
          shares={rc.posShares}
          onPositionChanged={rc.refreshCurrentPosition}
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
        <aside
          id="rcai-trades-panel"
          style={{
            width: 380, flex: 'none', borderLeft: '1px solid var(--border)', background: 'var(--bg-secondary)',
            position: 'relative', overflow: 'hidden',
          }}
        >
          <TradesTab activeTicker={rc.ticker} onSelectTicker={rc.switchTicker} />
        </aside>
      </main>
    </div>
  );
}

export default LiveApp;
