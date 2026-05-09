/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { CustomerInfoCard } from "@club_management_pos_ui/components/customer_info_card/customer_info_card";

// Register CustomerInfoCard as a sub-component of ProductScreen
ProductScreen.components = {
    ...ProductScreen.components,
    CustomerInfoCard,
};
