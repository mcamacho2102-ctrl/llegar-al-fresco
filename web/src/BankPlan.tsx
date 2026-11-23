import { BankOption, BankPlan, Footfall, fmt } from "./model";

const countLabel = (reading: Footfall) =>
  reading.count === null
    ? "Sin registros en esa franja"
    : reading.kind === "permanent"
      ? fmt(reading.count) + " pasos/h de media"
      : fmt(reading.count) + " pasos en la campaña";

export default function BankPlanResults({
  plan,
  onSimulate,
  busy,
}: {
  plan: BankPlan;
  onSimulate: (option: BankOption) => void;
  busy: boolean;
}) {
  return (
    <section
      id="priorizar-bancos"
      className="results bank-plan"
      aria-label="Ubicaciones para bancos"
    >
      <div className="section-title">
        <h2>Dónde instalar un banco</h2>
        {!!plan.options.length && (
          <button
            type="button"
            className="secondary"
            onClick={() => window.print()}
          >
            Imprimir comparación
          </button>
        )}
      </div>
      <p>
        En un radio de {fmt(plan.radiusM)} m, comparamos{" "}
        <strong>{plan.sitesTested} ubicaciones</strong> con el mismo destino y
        un máximo de <strong>{fmt(plan.restM)} m sin descanso</strong>.{" "}
        {plan.baselinePaths} de {plan.completed} portales tenían una ruta que
        cumplía el límite antes de la intervención.
      </p>
      {plan.completed < plan.sample && (
        <p className="form-note">
          {plan.sample - plan.completed} de {plan.sample} portales quedaron
          fuera de la comparación por el límite de cálculo.
        </p>
      )}
      {plan.olderInSampleSections !== null && (
        <p className="form-note">
          En las secciones de la muestra residen{" "}
          {fmt(plan.olderInSampleSections)} personas de 65 años o más.
        </p>
      )}
      {!plan.options.length && (
        <p>
          No encontramos puntos candidatos en los recorridos estudiados. Prueba
          otro radio, destino o límite de descanso.
        </p>
      )}
      {!!plan.options.length && (
        <>
          {!plan.options.some(
            (option) => option.newPaths > 0 || option.reducedGaps > 0,
          ) && (
            <p>
              Los puntos evaluados aportan poca mejora a los recorridos de esta
              muestra.
            </p>
          )}
          <ol className="bank-options">
            {plan.options.map((option, index) => (
              <li key={option.id}>
                <div className="bank-option-title">
                  <span aria-hidden="true">{index + 1}</span>
                  <h3>{option.label}</h3>
                </div>
                <p>
                  <strong>
                    {option.newPaths} de {plan.completed}
                  </strong>{" "}
                  portales ganan una ruta dentro del límite.
                </p>
                {option.lostPaths > 0 && (
                  <p className="form-note">
                    {option.lostPaths} dejan de tener una ruta encontrada en
                    esta simulación.
                  </p>
                )}
                <dl>
                  <div>
                    <dt>Tramo más largo sin descanso</dt>
                    <dd>
                      Se acorta en {option.reducedGaps} de {option.pairedPaths}{" "}
                      rutas comparables.
                      {option.medianReductionM !== null && (
                        <>
                          {" "}
                          Donde se acorta, lo hace una mediana de{" "}
                          {fmt(option.medianReductionM)} m.
                        </>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Residentes de 65 años o más</dt>
                    <dd>
                      {option.olderInNewSections === null
                        ? "Sin dato"
                        : `${fmt(option.olderInNewSections)} en ${option.newSections} secciones con nuevas rutas`}
                    </dd>
                  </div>
                  <div>
                    <dt>Ancho y sol en el tramo</dt>
                    <dd>
                      {option.widthM === null
                        ? "Ancho desconocido"
                        : `Ancho disponible en la fuente ${fmt(option.widthM)} m`}
                      {" · "}
                      {option.sunFraction === null
                        ? "Sin datos de sol"
                        : option.sunFraction === 0
                          ? "Sin sol directo estimado"
                          : option.sunFraction === 1
                            ? "Sol directo estimado"
                            : "Sol parcial estimado"}
                    </dd>
                  </div>
                  <div>
                    <dt>Aforo</dt>
                    <dd>
                      {option.footfall
                        ? countLabel(option.footfall)
                        : "Aforo del tramo desconocido"}
                    </dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => onSimulate(option)}
                >
                  Simular banco {index + 1} en el mapa
                </button>
              </li>
            ))}
          </ol>
          <p className="form-note">
            El orden prima el acceso, seguido del recorte de los tramos sin
            descanso y el padrón de las secciones que ganan acceso. Los
            recuentos de acceso se refieren a portales de la muestra. Comprueba
            en calle el espacio libre alrededor del asiento.
          </p>
        </>
      )}
      <h3>Aforos del entorno</h3>
      <p className="form-note">
        Los puntos morados marcan mediciones. La edad procede del padrón. Los
        aforos cuentan pasos y se presentan con su periodo. Los puntos de
        campaña se sitúan por el portal publicado.
      </p>
      {plan.footfall.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Punto de medida</th>
                <th>Afluencia observada</th>
                <th>Periodo</th>
              </tr>
            </thead>
            <tbody>
              {plan.footfall.map((reading) => (
                <tr key={reading.id}>
                  <td>
                    <a href={reading.source} target="_blank" rel="noreferrer">
                      {reading.label}
                    </a>
                    {reading.side && <small> · {reading.side}</small>}
                  </td>
                  <td>{countLabel(reading)}</td>
                  <td>
                    {reading.period ?? "Sin registros"}
                    {reading.kind === "permanent" && (
                      <small>
                        {" "}
                        · {reading.dayType} a las {reading.hour} ·{" "}
                        {reading.days} días con dato
                      </small>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Sin puntos de aforo localizados dentro del radio.</p>
      )}
    </section>
  );
}
