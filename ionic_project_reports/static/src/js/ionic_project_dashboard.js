import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class IonicProjectDashboard extends Component {
    static template = "ionic_project_reports.ProjectDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loaded: false,
            kpis: {},
            sectors: [],
        });
        this.env.config.setDisplayName(_t("Ionic Project Dashboard"));
        onWillStart(async () => {
            const data = await this.orm.call("ionic.project.dashboard", "get_dashboard_data", []);
            this.state.kpis = data.kpis;
            this.state.sectors = data.sectors;
            this.state.loaded = true;
        });
    }
}

registry.category("actions").add("ionic_project_dashboard", IonicProjectDashboard);
