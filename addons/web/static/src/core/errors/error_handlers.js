/** @odoo-module **/

import { browser } from "../browser/browser";
import { isIOS } from "../browser/feature_detection";
import { session } from "../../session";
import { ConnectionLostError, RPCError } from "../network/rpc_service";
import { registry } from "../registry";
import {
    ClientErrorDialog,
    ErrorDialog,
    NetworkErrorDialog,
    RPCErrorDialog,
} from "./error_dialogs";
import { UncaughtClientError, UncaughtCorsError, UncaughtPromiseError } from "./error_service";

/**
 * @typedef {import("../../env").OdooEnv} OdooEnv
 * @typedef {import("./error_service").UncaughtError} UncaughError
 */

const errorHandlerRegistry = registry.category("error_handlers");
const errorDialogRegistry = registry.category("error_dialogs");
const errorNotificationRegistry = registry.category("error_notifications");

// -----------------------------------------------------------------------------
// CORS errors
// -----------------------------------------------------------------------------

/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @returns {boolean}
 */
function corsErrorHandler(env, error) {
    if (error instanceof UncaughtCorsError) {
        // In Safari 16.4+ (as of Jun 14th 2023), an error occurs
        // when going back and forward through the browser when the
        // cache is enabled. A feedback has been reported but in the
        // meantime, hide any script error in these versions.
        if (isIOS() && session.is_frontend && odoo.debug !== "assets") {
            return true;
        }
        env.services.dialog.add(NetworkErrorDialog, {
            traceback: error.traceback,
            message: error.message,
            name: error.name,
        });
        return true;
    }
}
errorHandlerRegistry.add("corsErrorHandler", corsErrorHandler, { sequence: 95 });

// -----------------------------------------------------------------------------
// Client errors
// -----------------------------------------------------------------------------

/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @returns {boolean}
 */
function clientErrorHandler(env, error) {
    if (error instanceof UncaughtClientError) {
        env.services.dialog.add(ClientErrorDialog, {
            traceback: error.traceback,
            message: error.message,
            name: error.name,
        });
        return true;
    }
}
errorHandlerRegistry.add("clientErrorHandler", clientErrorHandler, { sequence: 96 });

// -----------------------------------------------------------------------------
// RPC errors
// -----------------------------------------------------------------------------

/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @param {Error} originalError
 * @returns {boolean}
 */
export function rpcErrorHandler(env, error, originalError) {
    if (!(error instanceof UncaughtPromiseError)) {
        return false;
    }
    if (originalError instanceof RPCError) {
        // When an error comes from the server, it can have an exeption name.
        // (or any string truly). It is used as key in the error dialog from
        // server registry to know which dialog component to use.
        // It's how a backend dev can easily map its error to another component.
        // Note that for a client side exception, we don't use this registry
        // as we can directly assign a value to `component`.
        // error is here a RPCError
        error.unhandledRejectionEvent.preventDefault();
        const exceptionName = originalError.exceptionName;
        let ErrorComponent = originalError.Component;
        if (!ErrorComponent && exceptionName) {
            if (errorNotificationRegistry.contains(exceptionName)) {
                const notif = errorNotificationRegistry.get(exceptionName);
                env.services.notification.add(notif.message || originalError.data.message, notif);
                return true;
            }
            if (errorDialogRegistry.contains(exceptionName)) {
                ErrorComponent = errorDialogRegistry.get(exceptionName);
            }
        }
        if (!ErrorComponent && originalError.data.context) {
            const exceptionClass = originalError.data.context.exception_class;
            if (errorDialogRegistry.contains(exceptionClass)) {
                ErrorComponent = errorDialogRegistry.get(exceptionClass);
            }
        }

        env.services.dialog.add(ErrorComponent || RPCErrorDialog, {
            traceback: error.traceback,
            message: originalError.message,
            name: originalError.name,
            exceptionName: originalError.exceptionName,
            data: originalError.data,
            subType: originalError.subType,
            code: originalError.code,
            type: originalError.type,
        });
        return true;
    }
}
errorHandlerRegistry.add("rpcErrorHandler", rpcErrorHandler, { sequence: 97 });

// -----------------------------------------------------------------------------
// Lost connection errors
// -----------------------------------------------------------------------------

let connectionLostNotifRemove = null;
/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @param {Error} originalError
 * @returns {boolean}
 */
export function lostConnectionHandler(env, error, originalError) {
    if (!(error instanceof UncaughtPromiseError)) {
        return false;
    }
    if (originalError instanceof ConnectionLostError) {
        if (connectionLostNotifRemove) {
            // notification already displayed (can occur if there were several
            // concurrent rpcs when the connection was lost)
            return true;
        }
        connectionLostNotifRemove = env.services.notification.add(
            env._t("Connection lost. Trying to reconnect..."),
            { sticky: true }
        );
        let delay = 2000;
        browser.setTimeout(function checkConnection() {
            env.services
                .rpc("/web/webclient/version_info", {})
                .then(function () {
                    if (connectionLostNotifRemove) {
                        connectionLostNotifRemove();
                        connectionLostNotifRemove = null;
                    }
                    env.services.notification.add(
                        env._t("Connection restored. You are back online."),
                        {
                            type: "info",
                        }
                    );
                })
                .catch(() => {
                    // exponential backoff, with some jitter
                    delay = delay * 1.5 + 500 * Math.random();
                    browser.setTimeout(checkConnection, delay);
                });
        }, delay);
        return true;
    }
}
errorHandlerRegistry.add("lostConnectionHandler", lostConnectionHandler, { sequence: 98 });

// -----------------------------------------------------------------------------
// Empty rejection errors
// -----------------------------------------------------------------------------

/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @returns {boolean}
 */
function emptyRejectionErrorHandler(env, error) {
    if (!(error instanceof UncaughtPromiseError)) {
        return false;
    }
    env.services.dialog.add(ClientErrorDialog, {
        traceback: error.traceback,
        message: error.message,
        name: error.name,
    });
    return true;
}
errorHandlerRegistry.add("emptyRejectionErrorHandler", emptyRejectionErrorHandler, {
    sequence: 99,
});

// -----------------------------------------------------------------------------
// Default handler
// -----------------------------------------------------------------------------

/**
 * @param {OdooEnv} env
 * @param {UncaughError} error
 * @returns {boolean}
 */
function defaultHandler(env, error) {
    env.services.dialog.add(ErrorDialog, {
        traceback: error.traceback,
        message: error.message,
        name: error.name,
    });
    return true;
}
errorHandlerRegistry.add("defaultHandler", defaultHandler, { sequence: 100 });
