odoo.define('survey.session_manage', function (require) {
'use strict';

var publicWidget = require('web.public.widget');
var SurveySessionChart = require('survey.session_chart');
var SurveySessionTextAnswers = require('survey.session_text_answers');
var SurveySessionLeaderBoard = require('survey.session_leaderboard');
var core = require('web.core');
var _t = core._t;

publicWidget.registry.SurveySessionManage = publicWidget.Widget.extend({
    selector: '.o_survey_session_manage',
    events: {
        'click .o_survey_session_copy': '_onCopySessionLink',
        'click .o_survey_session_navigation_next, .o_survey_session_start': '_onNext',
        'click .o_survey_session_navigation_previous': '_onBack',
        'click .o_survey_session_close': '_onEndSessionClick',
    },

    /**
     * Overridden to set a few properties that come from the python template rendering.
     *
     * We also handle the timer IF we're not "transitioning", meaning a fade out of the previous
     * $el to the next question (the fact that we're transitioning is in the isRpcCall data).
     * If we're transitioning, the timer is handled manually at the end of the transition.
     */
    start: function () {
        var self = this;
        this.fadeInOutTime = 500;
        return this._super.apply(this, arguments).then(function () {
            // general survey props
            self.surveyId = self.$el.data('surveyId');
            self.surveyAccessToken = self.$el.data('surveyAccessToken');
            self.isStartScreen = self.$el.data('isStartScreen');
            self.isFirstQuestion = self.$el.data('isFirstQuestion');
            self.isLastQuestion = self.$el.data('isLastQuestion');
            // scoring props
            self.isScoredQuestion = self.$el.data('isScoredQuestion');
            self.sessionShowLeaderboard = self.$el.data('sessionShowLeaderboard');
            self.hasCorrectAnswers = self.$el.data('hasCorrectAnswers');
            // display props
            self.showBarChart = self.$el.data('showBarChart');
            self.showTextAnswers = self.$el.data('showTextAnswers');

            var isRpcCall = self.$el.data('isRpcCall');
            if (!isRpcCall) {
                self._startTimer();
                $(document).on('keydown', self._onKeyDown.bind(self));
            }

            self._setupIntervals();
            self._setupCurrentScreen();
            var setupPromises = [];
            setupPromises.push(self._setupTextAnswers());
            setupPromises.push(self._setupChart());
            setupPromises.push(self._setupLeaderboard());

            return Promise.all(setupPromises);
        });
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * Copies the survey URL link to the clipboard.
     * We use 'ClipboardJS' to avoid having to print the URL in a standard text input
     *
     * @param {MouseEvent} ev
     */
    _onCopySessionLink: function (ev) {
        var self = this;
        ev.preventDefault();

        var $clipboardBtn = this.$('.o_survey_session_copy');

        $clipboardBtn.popover({
            placement: 'right',
            container: 'body',
            offset: '0, 3',
            content: function () {
                return _t("Copied !");
            }
        });

        var clipboard = new ClipboardJS('.o_survey_session_copy', {
            text: function () {
                return self.$('.o_survey_session_copy_url').val();
            },
            container: this.el
        });

        clipboard.on('success', function () {
            clipboard.destroy();
            $clipboardBtn.popover('show');
            _.delay(function () {
                $clipboardBtn.popover('hide');
            }, 800);
        });

        clipboard.on('error', function (e) {
            clipboard.destroy();
        });
    },

    /**
     * Listeners for keyboard arrow / spacebar keys.
     *
     * - 39 = arrow-right
     * - 32 = spacebar
     * - 37 = arrow-left
     *
     * @param {KeyboardEvent} ev
     */
    _onKeyDown: function (ev) {
        var keyCode = ev.keyCode;

        if (keyCode === 39 || keyCode === 32) {
            this._onNext(ev);
        } else if (keyCode === 37) {
            this._onBack(ev);
        }
    },

    /**
     * Handles the "next screen" behavior.
     * It happens when the host uses the keyboard key / button to go to the next screen.
     * The result depends on the current screen we're on.
     *
     * Possible values of the "next screen" to display are:
     * - 'userInputs' when going from a question to the display of attendees' survey.user_input.line
     *   for that question.
     * - 'results' when going from the inputs to the actual correct / incorrect answers of that
     *   question. Only used for scored simple / multiple choice questions.
     * - 'leaderboard' (or 'leaderboardFinal') when going from the correct answers of a question to
     *   the leaderboard of attendees. Only used for scored simple / multiple choice questions.
     * - If it's not one of the above: we go to the next question, or end the session if we're on
     *   the last question of this session.
     *
     * See '_getNextScreen' for a detailed logic.
     *
     * @param {Event} ev
     */
    _onNext: function (ev) {
        ev.preventDefault();

        var screenToDisplay = this._getNextScreen();

        if (screenToDisplay === 'userInputs') {
            this._setShowInputs(true);
        } else if (screenToDisplay === 'results') {
            this._setShowAnswers(true);
            // when showing results, stop refreshing answers
            clearInterval(this.resultsRefreshInterval);
            delete this.resultsRefreshInterval;
        } else if (['leaderboard', 'leaderboardFinal'].includes(screenToDisplay)
                   && !['leaderboard', 'leaderboardFinal'].includes(this.currentScreen)) {
            if (this.isLastQuestion) {
                this.$('.o_survey_session_navigation_next').addClass('d-none');
            }
            this.leaderBoard.showLeaderboard(true, this.isScoredQuestion);
        } else {
            if (!this.isLastQuestion) {
                this._nextQuestion();
            } else if (!this.sessionShowLeaderboard) {
                // If we have no leaderboard to show, directly end the session
                this.$('.o_survey_session_close').click();
            }
        }

        this.currentScreen = screenToDisplay;
    },

    /**
     * Reverse behavior of '_onNext'.
     *
     * @param {Event} ev
     */
    _onBack: function (ev) {
        ev.preventDefault();

        var screenToDisplay = this._getPreviousScreen();

        if (screenToDisplay === 'question') {
            this._setShowInputs(false);
        } else if (screenToDisplay === 'userInputs') {
            this._setShowAnswers(false);
            // resume refreshing answers if necessary
            if (!this.resultsRefreshInterval) {
                this.resultsRefreshInterval = setInterval(this._refreshResults.bind(this), 2000);
            }
        } else if (screenToDisplay === 'results') {
            if (this.leaderBoard) {
                this.leaderBoard.hideLeaderboard();
            }
            // when showing results, stop refreshing answers
            clearInterval(this.resultsRefreshInterval);
            delete this.resultsRefreshInterval;
        } else if (screenToDisplay === 'previousQuestion') {
            if (this.isFirstQuestion) {
                return;  // nothing to go back to, we're on the first question
            }
            this._nextQuestion(true);
        }

        this.currentScreen = screenToDisplay;
    },

    /**
     * Marks this session as 'done' and redirects the user to the results based on the clicked link.
     *
     * @param {MouseEvent} ev
     * @private
    */
    _onEndSessionClick: function (ev) {
        var self = this;
        ev.preventDefault();

        this._rpc({
            model: 'survey.survey',
            method: 'action_end_session',
            args: [[this.surveyId]],
        }).then(function () {
            if ($(ev.currentTarget).data('showResults')) {
                document.location = _.str.sprintf(
                    '/survey/results/%s',
                    self.surveyId
                );
            } else {
                window.history.back();
            }
        });
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Business logic that determines the 'next screen' based on the current screen and the question
     * configuration.
     *
     * Breakdown of use cases:
     * - If we're on the 'question' screen, and the question is scored, we move to the 'userInputs'
     * - If we're on the 'question' screen and it's NOT scored, then we move to
     *     - 'results' if the question has correct / incorrect answers
     *       (but not scored, which is kind of a corner case)
     *     - 'nextQuestion' otherwise
     * - If we're on the 'userInputs' screen and the question has answers, we move to the 'results'
     * - If we're on the 'results' and the question is scored, we move to the 'leaderboard'
     * - In all other cases, we show the next question
     * - (Small exception for the last question: we show the "final leaderboard")
     *
     * (For details about which screen shows what, see '_onNext')
     */
    _getNextScreen: function () {
        if (this.currentScreen === 'question' && this.isScoredQuestion) {
            return 'userInputs';
        } else if (this.hasCorrectAnswers && ['question', 'userInputs'].includes(this.currentScreen)) {
            return 'results';
        } else if (this.sessionShowLeaderboard) {
            if (['question', 'userInputs', 'results'].includes(this.currentScreen) && this.isScoredQuestion) {
                return 'leaderboard';
            } else if (this.isLastQuestion) {
                return 'leaderboardFinal';
            }
        }
        return 'nextQuestion';
    },

    /**
     * Reverse behavior of '_getNextScreen'.
     *
     * @param {Event} ev
     */
    _getPreviousScreen: function () {
        if (this.currentScreen === 'userInputs' && this.isScoredQuestion) {
            return 'question';
        } else if ((this.currentScreen === 'results' && this.isScoredQuestion) ||
                  (this.currentScreen === 'leaderboard' && !this.isScoredQuestion) ||
                  (this.currentScreen === 'leaderboardFinal' && this.isScoredQuestion)) {
            return 'userInputs';
        } else if ((this.currentScreen === 'leaderboard' && this.isScoredQuestion) ||
                  (this.currentScreen === 'leaderboardFinal' && !this.isScoredQuestion)){
            return 'results';
        }

        return 'previousQuestion';
    },

    /**
    * We use a fade in/out mechanism to display the next question of the session.
    *
    * The fade out happens at the same moment as the _rpc to get the new question template.
    * When they're both finished, we update the HTML of this widget with the new template and then
    * fade in the updated question to the user.
    *
    * The timer (if configured) starts at the end of the fade in animation.
    *
    * @param {MouseEvent} ev
    * @private
    */
    _nextQuestion: function (goBack) {
        var self = this;

        this.isStartScreen = false;
        if (this.surveyTimerWidget) {
            this.surveyTimerWidget.destroy();
        }

        var resolveFadeOut;
        var fadeOutPromise = new Promise(function (resolve, reject) { resolveFadeOut = resolve; });
        this.$el.fadeOut(this.fadeInOutTime, function () {
            resolveFadeOut();
        });

        var nextQuestionPromise = this._rpc({
            route: _.str.sprintf('/survey/session/next_question/%s', self.surveyAccessToken),
            params: {
                'go_back': goBack,
            }
        });

        // avoid refreshing results while transitioning
        if (this.resultsRefreshInterval) {
            clearInterval(this.resultsRefreshInterval);
            delete this.resultsRefreshInterval;
        }

        Promise.all([fadeOutPromise, nextQuestionPromise]).then(async function (results) {
            if (results[1]) {
                var $renderedTemplate = $(results[1]);
                self.$el.replaceWith($renderedTemplate);

                // Ensure new question is fully loaded before force loading previous question screen.
                await self.attachTo($renderedTemplate);
                if (goBack) {
                    // As we arrive on "question" screen, simulate going to the results screen or leaderboard.
                    self._setShowInputs(true);
                    self._setShowAnswers(true);
                    if (self.sessionShowLeaderboard && self.isScoredQuestion) {
                        self.currentScreen = 'leaderboard';
                        self.leaderBoard.showLeaderboard(false, self.isScoredQuestion);
                    } else {
                        self.currentScreen = 'results';
                        self._refreshResults();
                    }
                } else {
                    self._startTimer();
                }
                self.$el.fadeIn(self.fadeInOutTime);
            } else if (self.sessionShowLeaderboard) {
                // Display last screen if leaderboard activated
                self.isLastQuestion = true;
                self._setupLeaderboard().then(function () {
                    self.$('.o_survey_session_leaderboard_title').text(_t('Final Leaderboard'));
                    self.$('.o_survey_session_navigation_next').addClass('d-none');
                    self.$('.o_survey_leaderboard_buttons').removeClass('d-none');
                    self.leaderBoard.showLeaderboard(false, false);
                });
            } else {
                self.$('.o_survey_session_close').click();
            }
        });
    },

    /**
     * Will start the question timer so that the host may know when the question is done to display
     * the results and the leaderboard.
     *
     * If the question is scored, the timer ending triggers the display of attendees inputs.
     */
    _startTimer: function () {
        var self = this;
        var $timer = this.$('.o_survey_timer');

        if ($timer.length) {
            var timeLimitMinutes = this.$el.data('timeLimitMinutes');
            var timer = this.$el.data('timer');
            this.surveyTimerWidget = new publicWidget.registry.SurveyTimerWidget(this, {
                'timer': timer,
                'timeLimitMinutes': timeLimitMinutes
            });
            this.surveyTimerWidget.attachTo($timer);
            this.surveyTimerWidget.on('time_up', this, function () {
                if (self.currentScreen === 'question' && this.isScoredQuestion) {
                    self.$('.o_survey_session_navigation_next').click();
                }
            });
        }
    },

    /**
     * Refreshes the question results.
     *
     * What we get from this call:
     * - The 'question statistics' used to display the bar chart when appropriate
     * - The 'user input lines' that are used to display text/date/datetime answers on the screen
     * - The number of answers, useful for refreshing the progress bar
     */
    _refreshResults: function () {
        var self = this;

        return this._rpc({
            route: _.str.sprintf('/survey/session/results/%s', self.surveyAccessToken)
        }).then(function (questionResults) {
            if (questionResults) {
                self.attendeesCount = questionResults.attendees_count;

                if (self.resultsChart && questionResults.question_statistics_graph) {
                    self.resultsChart.updateChart(JSON.parse(questionResults.question_statistics_graph));
                } else if (self.textAnswers) {
                    self.textAnswers.updateTextAnswers(questionResults.input_line_values);
                }

                var max = self.attendeesCount > 0 ? self.attendeesCount : 1;
                var percentage = Math.min(Math.round((questionResults.answer_count / max) * 100), 100);
                self.$('.progress-bar').css('width', `${percentage}%`);

                if (self.attendeesCount && self.attendeesCount > 0) {
                    var answerCount = Math.min(questionResults.answer_count, self.attendeesCount);
                    self.$('.o_survey_session_answer_count').text(answerCount);
                    self.$('.progress-bar.o_survey_session_progress_small span').text(
                        `${answerCount} / ${self.attendeesCount}`
                    );
                }
            }

            return Promise.resolve();
        }, function () {
            // on failure, stop refreshing
            clearInterval(self.resultsRefreshInterval);
            delete self.resultsRefreshInterval;
        });
    },

    /**
     * We refresh the attendees count every 2 seconds while the user is on the start screen.
     *
     */
    _refreshAttendeesCount: function () {
        var self = this;

        return self._rpc({
            model: 'survey.survey',
            method: 'read',
            args: [[self.surveyId], ['session_answer_count']],
        }).then(function (result) {
            if (result && result.length === 1){
                self.$('.o_survey_session_attendees_count').text(
                    result[0].session_answer_count
                );
            }
        }, function () {
            // on failure, stop refreshing
            clearInterval(self.attendeesRefreshInterval);
        });
    },

    /**
     * For simple/multiple choice questions, we display a bar chart with:
     *
     * - answers of attendees
     * - correct / incorrect answers when relevant
     *
     * see SurveySessionChart widget doc for more information.
     *
     */
    _setupChart: function () {
        if (this.resultsChart) {
            this.resultsChart.setElement(null);
            this.resultsChart.destroy();
            delete this.resultsChart;
        }

        if (!this.isStartScreen && this.showBarChart) {
            this.resultsChart = new SurveySessionChart(this, {
                questionType: this.$el.data('questionType'),
                answersValidity: this.$el.data('answersValidity'),
                hasCorrectAnswers: this.hasCorrectAnswers,
                questionStatistics: this.$el.data('questionStatistics'),
                showInputs: this.showInputs
            });

            return this.resultsChart.attachTo(this.$('.o_survey_session_chart'));
        } else {
            return Promise.resolve();
        }
    },

    /**
     * Leaderboard of all the attendees based on their score.
     * see SurveySessionLeaderBoard widget doc for more information.
     *
     */
    _setupLeaderboard: function () {
        if (this.leaderBoard) {
            this.leaderBoard.setElement(null);
            this.leaderBoard.destroy();
            delete this.leaderBoard;
        }

        if (this.isScoredQuestion || this.isLastQuestion) {
            this.leaderBoard = new SurveySessionLeaderBoard(this, {
                surveyAccessToken: this.surveyAccessToken,
                sessionResults: this.$('.o_survey_session_results')
            });

            return this.leaderBoard.attachTo(this.$('.o_survey_session_leaderboard'));
        } else {
            return Promise.resolve();
        }
    },

    /**
     * Shows attendees answers for char_box/date and datetime questions.
     * see SurveySessionTextAnswers widget doc for more information.
     *
     */
    _setupTextAnswers: function () {
        if (this.textAnswers) {
            this.textAnswers.setElement(null);
            this.textAnswers.destroy();
            delete this.textAnswers;
        }

        if (!this.isStartScreen && this.showTextAnswers) {
            this.textAnswers = new SurveySessionTextAnswers(this, {
                questionType: this.$el.data('questionType')
            });

            return this.textAnswers.attachTo(this.$('.o_survey_session_text_answers_container'));
        } else {
            return Promise.resolve();
        }
    },

    /**
     * Setup the 2 refresh intervals of 2 seconds for our widget:
     * - The refresh of attendees count (only on the start screen)
     * - The refresh of results (used for chart/text answers/progress bar)
     */
    _setupIntervals: function () {
        this.attendeesCount = this.$el.data('attendeesCount') ? this.$el.data('attendeesCount') : 0;

        if (this.isStartScreen) {
            this.attendeesRefreshInterval = setInterval(this._refreshAttendeesCount.bind(this), 2000);
        } else {
            if (this.attendeesRefreshInterval) {
                clearInterval(this.attendeesRefreshInterval);
            }

            if (!this.resultsRefreshInterval) {
                this.resultsRefreshInterval = setInterval(this._refreshResults.bind(this), 2000);
            }
        }
    },

    /**
     * Setup current screen based on question properties.
     * If it's a non-scored question with a chart, we directly display the user inputs.
     */
    _setupCurrentScreen: function () {
        if (this.isStartScreen) {
            this.currentScreen = 'startScreen';
        } else if (!this.isScoredQuestion && this.showBarChart) {
            this.currentScreen = 'userInputs';
        } else {
            this.currentScreen = 'question';
        }

        this.$('.o_survey_session_navigation_previous').toggleClass('d-none', !!this.isFirstQuestion);

        this._setShowInputs(this.currentScreen === 'userInputs');
    },

    /**
     * When we go from the 'question' screen to the 'userInputs' screen, we toggle this boolean
     * and send the information to the chart.
     * The chart will show attendees survey.user_input.lines.
     *
     * @param {Boolean} showInputs
     */
    _setShowInputs(showInputs) {
        this.showInputs = showInputs;

        if (this.resultsChart) {
            this.resultsChart.setShowInputs(showInputs);
            this.resultsChart.updateChart();
        }
    },

    /**
     * When we go from the 'userInputs' screen to the 'results' screen, we toggle this boolean
     * and send the information to the chart.
     * The chart will show the question survey.question.answers.
     * (Only used for simple / multiple choice questions).
     *
     * @param {Boolean} showAnswers
     */
    _setShowAnswers(showAnswers) {
        this.showAnswers = showAnswers;

        if (this.resultsChart) {
            this.resultsChart.setShowAnswers(showAnswers);
            this.resultsChart.updateChart();
        }
    }
});

return publicWidget.registry.SurveySessionManage;

});
