import { useState } from 'react';
import type {
  ModifierGroupView,
  ModifierOptionView,
} from '@restaurant-engine/api-client';
import { asApiFailure } from '../../api/failure';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { scopedLabel } from '../../components/ScopedLabel';
import { mapFailure, type FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { formatMinor } from '../money';
import {
  useCreateGroup,
  useCreateOption,
  useDeleteGroup,
  useDeleteOption,
  useModifierGroups,
  useReorderGroups,
  useUpdateGroup,
  useUpdateOption,
} from '../modifierData';
import { ruleSummary, unsatisfiableReason } from '../modifierRules';
import {
  ModifierGroupFormDialog,
  type GroupFormValues,
} from './ModifierGroupFormDialog';
import {
  ModifierOptionFormDialog,
  type OptionFormValues,
} from './ModifierOptionFormDialog';
import { ReorderList } from './ReorderList';
import styles from '../menu.module.css';

type Dialog =
  | { kind: 'group-create' }
  | { kind: 'group-edit'; group: ModifierGroupView }
  | { kind: 'group-delete'; group: ModifierGroupView }
  | { kind: 'option-create'; group: ModifierGroupView }
  | { kind: 'option-edit'; option: ModifierOptionView }
  | { kind: 'option-delete'; option: ModifierOptionView };

/**
 * Option groups for one menu item.
 *
 * Groups belong to exactly one item and options to exactly one group
 * (ADR-017 D2), so there is deliberately no "attach an existing group"
 * affordance — no shared modifier library exists in M3, and offering one
 * would promise something the contract cannot do.
 *
 * Satisfiability is shown as an advisory and never blocks a save: a legal
 * but currently unsatisfiable configuration is always storable (ruling D5).
 * The warning explains the consequence truthfully instead of pretending the
 * configuration is invalid.
 */
export function ModifierGroupsSection({
  businessId,
  itemId,
  currency,
  canWrite,
}: {
  businessId: string;
  itemId: string;
  currency: string;
  canWrite: boolean;
}) {
  const groups = useModifierGroups(businessId, itemId);
  const notify = useNotify();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [reordering, setReordering] = useState(false);

  const createGroup = useCreateGroup(businessId, itemId);
  const updateGroup = useUpdateGroup(businessId, itemId);
  const deleteGroup = useDeleteGroup(businessId, itemId);
  const reorderGroups = useReorderGroups(businessId, itemId);
  const createOption = useCreateOption(businessId, itemId);
  const updateOption = useUpdateOption(businessId, itemId);
  const deleteOption = useDeleteOption(businessId, itemId);

  if (groups.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading options…
      </p>
    );
  }
  if (groups.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The options could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void groups.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const list = groups.data.groups;

  function close(message: string) {
    setDialog(null);
    setFailure(null);
    notify({ message });
  }

  function fail(fallback: string) {
    return (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), fallback));
    };
  }

  return (
    <section aria-labelledby="modifiers-title" className={styles.modifiers}>
      <div className={styles.pageHead}>
        <h3 id="modifiers-title">Options and add-ons</h3>
        {canWrite && (
          <div className={styles.actionsInline}>
            {list.length > 1 && !reordering && (
              <button
                type="button"
                className={styles.secondary}
                onClick={() => {
                  setReordering(true);
                }}
              >
                Reorder groups
              </button>
            )}
            <button
              type="button"
              className={styles.submit}
              onClick={() => {
                setFailure(null);
                setDialog({ kind: 'group-create' });
              }}
            >
              New group
            </button>
          </div>
        )}
      </div>

      {failure !== null && <ErrorSummary failure={failure} />}

      {reordering && (
        <ReorderList
          noun="group"
          entries={list.map((group) => ({ id: group.id, name: group.name }))}
          pending={reorderGroups.isPending}
          error={null}
          onCancel={() => {
            setReordering(false);
          }}
          onSave={(orderedIds) => {
            reorderGroups.mutate(orderedIds, {
              onSuccess: () => {
                setReordering(false);
                notify({ message: 'Group order saved.' });
              },
              onError: (error: unknown) => {
                setReordering(false);
                setFailure(
                  mapFailure(
                    asApiFailure(error),
                    'The group order could not be saved. The options have been refreshed.',
                  ),
                );
                void groups.refetch();
              },
            });
          }}
        />
      )}

      {list.length === 0 ? (
        <p className={styles.empty}>
          This item has no option groups. Add one if customers choose a size, a
          spice level, or extras.
        </p>
      ) : (
        <ol className={styles.groupList}>
          {list.map((group) => {
            const warning = unsatisfiableReason(group);
            return (
              <li key={group.id} className={styles.groupCard}>
                <div className={styles.categoryHead}>
                  <h4 className={styles.groupName}>{group.name}</h4>
                  <p className={styles.count}>{ruleSummary(group)}</p>
                </div>
                <p className={styles.count}>
                  {group.active_option_count === 1
                    ? '1 available choice'
                    : `${String(group.active_option_count)} available choices`}
                </p>

                {warning !== null && (
                  <p className={styles.warning}>
                    <strong>Not currently selectable.</strong> {warning}
                  </p>
                )}

                {group.options.length > 0 && (
                  <ul className={styles.optionList}>
                    {group.options.map((option) => (
                      <li key={option.id} className={styles.optionRow}>
                        <span className={styles.optionName}>{option.name}</span>
                        {!option.is_available && (
                          <span className={styles.chipSoldOut}>
                            Unavailable
                          </span>
                        )}
                        <span className={styles.optionPrice}>
                          {option.price_delta_minor === 0
                            ? 'No extra charge'
                            : `+ ${formatMinor(option.price_delta_minor, currency)}`}
                        </span>
                        {canWrite && (
                          <>
                            <button
                              type="button"
                              className={styles.quiet}
                              onClick={() => {
                                setFailure(null);
                                setDialog({ kind: 'option-edit', option });
                              }}
                              aria-label={scopedLabel('Edit', option.name)}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className={styles.quiet}
                              onClick={() => {
                                setFailure(null);
                                setDialog({ kind: 'option-delete', option });
                              }}
                              aria-label={scopedLabel('Delete', option.name)}
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}

                {canWrite && (
                  <div className={styles.categoryActions}>
                    <button
                      type="button"
                      className={styles.quiet}
                      onClick={() => {
                        setFailure(null);
                        setDialog({ kind: 'option-create', group });
                      }}
                      aria-label={scopedLabel('Add a choice to', group.name)}
                    >
                      Add a choice
                    </button>
                    <button
                      type="button"
                      className={styles.quiet}
                      onClick={() => {
                        setFailure(null);
                        setDialog({ kind: 'group-edit', group });
                      }}
                      aria-label={scopedLabel('Edit group', group.name)}
                    >
                      Edit group
                    </button>
                    <button
                      type="button"
                      className={styles.quiet}
                      onClick={() => {
                        setFailure(null);
                        setDialog({ kind: 'group-delete', group });
                      }}
                      aria-label={scopedLabel('Delete group', group.name)}
                    >
                      Delete group
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {(dialog?.kind === 'group-create' || dialog?.kind === 'group-edit') && (
        <ModifierGroupFormDialog
          group={dialog.kind === 'group-edit' ? dialog.group : undefined}
          pending={createGroup.isPending || updateGroup.isPending}
          failure={failure}
          onCancel={() => {
            setDialog(null);
            setFailure(null);
          }}
          onSubmit={(values: GroupFormValues) => {
            const body = {
              name: values.name,
              min_select: values.minSelect,
              max_select: values.maxSelect,
            };
            if (dialog.kind === 'group-create') {
              createGroup.mutate(body, {
                onSuccess: (created) => {
                  close(`Group “${created.name}” added.`);
                },
                onError: fail('The group could not be added.'),
              });
            } else {
              updateGroup.mutate(
                { groupId: dialog.group.id, body },
                {
                  onSuccess: (updated) => {
                    close(`Group “${updated.name}” saved.`);
                  },
                  onError: fail('The group could not be saved.'),
                },
              );
            }
          }}
        />
      )}

      {(dialog?.kind === 'option-create' || dialog?.kind === 'option-edit') && (
        <ModifierOptionFormDialog
          option={dialog.kind === 'option-edit' ? dialog.option : undefined}
          currency={currency}
          pending={createOption.isPending || updateOption.isPending}
          failure={failure}
          onCancel={() => {
            setDialog(null);
            setFailure(null);
          }}
          onSubmit={(values: OptionFormValues) => {
            if (dialog.kind === 'option-create') {
              createOption.mutate(
                {
                  groupId: dialog.group.id,
                  body: {
                    name: values.name,
                    price_delta_minor: values.priceDeltaMinor,
                  },
                },
                {
                  onSuccess: () => {
                    close(`“${values.name}” added.`);
                  },
                  onError: fail('The choice could not be added.'),
                },
              );
            } else {
              updateOption.mutate(
                {
                  optionId: dialog.option.id,
                  body: {
                    name: values.name,
                    price_delta_minor: values.priceDeltaMinor,
                    is_available: values.isAvailable,
                  },
                },
                {
                  onSuccess: () => {
                    close(`“${values.name}” saved.`);
                  },
                  onError: fail('The choice could not be saved.'),
                },
              );
            }
          }}
        />
      )}

      {dialog?.kind === 'group-delete' && (
        <ConfirmDialog
          title={`Delete ${dialog.group.name}?`}
          confirmLabel="Delete group"
          danger
          pending={deleteGroup.isPending}
          onCancel={() => {
            setDialog(null);
          }}
          onConfirm={() => {
            const { group } = dialog;
            deleteGroup.mutate(group.id, {
              onSuccess: () => {
                close(`Group “${group.name}” deleted.`);
              },
              onError: (error: unknown) => {
                setDialog(null);
                setFailure(
                  mapFailure(
                    asApiFailure(error),
                    'The group could not be deleted.',
                  ),
                );
              },
            });
          }}
        >
          <p>
            This cannot be undone.{' '}
            {dialog.group.options.length === 1
              ? 'Its 1 choice is deleted with it.'
              : `Its ${String(dialog.group.options.length)} choices are deleted with it.`}
          </p>
        </ConfirmDialog>
      )}

      {dialog?.kind === 'option-delete' && (
        <ConfirmDialog
          title={`Delete ${dialog.option.name}?`}
          confirmLabel="Delete choice"
          danger
          pending={deleteOption.isPending}
          onCancel={() => {
            setDialog(null);
          }}
          onConfirm={() => {
            const { option } = dialog;
            deleteOption.mutate(option.id, {
              onSuccess: () => {
                close(`“${option.name}” deleted.`);
              },
              onError: (error: unknown) => {
                setDialog(null);
                setFailure(
                  mapFailure(
                    asApiFailure(error),
                    'The choice could not be deleted.',
                  ),
                );
              },
            });
          }}
        >
          <p>
            This cannot be undone.
            {list.find((group) => group.id === dialog.option.group_id)
              ?.active_option_count === 1
              ? ' It is the last available choice in its group, so the group will stop being selectable until you add another.'
              : ''}
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
