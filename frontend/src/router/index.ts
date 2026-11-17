import { createRouter, createWebHistory } from "vue-router"
import AppLayout from "@/layouts/AppLayout.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: AppLayout,
      children: [
        { path: "", redirect: "/remittances" },
        {
          path: "remittances",
          component: () => import("@/views/remittance/RemittanceView.vue"),
        },
        {
          path: "shipments",
          component: () => import("@/views/shipment/ShipmentListView.vue"),
        },
        {
          path: "shipments/:id",
          component: () => import("@/views/shipment/ShipmentDetailView.vue"),
        },
        {
          path: "stores",
          component: () => import("@/views/store/StoreListView.vue"),
        },
        {
          path: "import",
          component: () => import("@/views/import/ImportView.vue"),
        },
        {
          path: "bank",
          component: () => import("@/views/bank/BankView.vue"),
        },
      ],
    },
  ],
})

router.afterEach((to) => {
  const titles: Record<string, string> = {
    "/remittances": "汇款月表",
    "/shipments": "发货单",
    "/stores": "门店",
    "/import": "导入",
    "/bank": "银行流水",
  }
  const matched = Object.keys(titles).find((path) => to.path.startsWith(path))
  document.title = matched ? `${titles[matched]} · 门店对账` : "门店对账"
})

export default router
