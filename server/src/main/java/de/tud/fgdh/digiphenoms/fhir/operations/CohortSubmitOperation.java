package de.tud.fgdh.digiphenoms.fhir.operations;

import ca.uhn.fhir.rest.annotation.Operation;
import ca.uhn.fhir.rest.annotation.OperationParam;
import de.tud.fgdh.digiphenoms.fhir.service.CohortSubmitService;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.CodeType;
import org.hl7.fhir.r4.model.Parameters;
import org.hl7.fhir.r4.model.StringType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * HAPI FHIR plain provider for the {@code $cohort-submit} system-level operation.
 *
 * <p>Registered automatically via Spring component scanning from the
 * {@code hapi.fhir.custom_bean_packages} configuration. Delegates all processing
 * to {@link CohortSubmitService}.</p>
 *
 * @see <a href="https://digiphenoms.tu-dresden.de/fhir/OperationDefinition/cohort-submit">
 *      OperationDefinition</a>
 */
@Component
public class CohortSubmitOperation {

    private static final Logger LOG = LoggerFactory.getLogger(CohortSubmitOperation.class);

    private final CohortSubmitService service;

    public CohortSubmitOperation(CohortSubmitService service) {
        this.service = service;
    }

    /**
     * Handle {@code POST /fhir/$cohort-submit}.
     *
     * @param inputBundle  FHIR Bundle (type=collection) with cohort resources
     * @param mode         import mode: "merge" (default) or "distinct"
     * @param cohortId     identifier of the cohort root group (default: "digiphenoms-ms-cohort")
     * @param batchLabel   human-readable label for this import batch
     * @return Parameters response with outcome, importGroup reference, and statistics
     */
    @Operation(name = "$cohort-submit", idempotent = false)
    public Parameters cohortSubmit(
            @OperationParam(name = "inputBundle") Bundle inputBundle,
            @OperationParam(name = "mode") CodeType mode,
            @OperationParam(name = "cohortId") StringType cohortId,
            @OperationParam(name = "batchLabel") StringType batchLabel) {

        LOG.info("$cohort-submit invoked — mode={}, cohortId={}, batchLabel={}",
                mode != null ? mode.getCode() : "merge",
                cohortId != null ? cohortId.getValue() : "(default)",
                batchLabel != null ? batchLabel.getValue() : "(auto)");

        return service.execute(
                inputBundle,
                mode != null ? mode.getCode() : "merge",
                cohortId != null ? cohortId.getValue() : null,
                batchLabel != null ? batchLabel.getValue() : null);
    }
}
